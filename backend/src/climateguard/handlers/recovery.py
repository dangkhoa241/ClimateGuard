"""Lambda (HTTP API + async worker): the recovery agent's routes (see recovery.py).

POST /recovery/{job}/analyze answers 202 at once and re-invokes this same function asynchronously
({"recovery_task": "analyze", "job": ...}) to do the work; the app polls GET /recovery/{job}.
Async retries are off in template.yaml: a failed job shows "try again" instead of being billed twice.
"""
import base64
import json
import logging
import os
import threading

from .. import budget, llm, ratelimit, recovery
from ..photos import PhotoError
from ..subscriptions import SignupError
from .api import _json_body, _resp, _source_ip

log = logging.getLogger()
JOBS_PER_IP_PER_HOUR = 6
MAX_PHOTO_BODY_CHARS = 2_100_000  # 1.5 MB JPEG as base64

try:  # cold start: model client during init (see handlers/ask.py)
    llm._client("meta")
except Exception as e:
    log.warning("model client not ready at init: %s", e)


def _start_worker(task: str, job: str) -> None:
    name = os.getenv("AWS_LAMBDA_FUNCTION_NAME")
    if name:
        import boto3

        boto3.client("lambda").invoke(FunctionName=name, InvocationType="Event",
                                      Payload=json.dumps({"recovery_task": task, "job": job}).encode())
    else:  # local dev server: a background thread
        threading.Thread(target=run_task, args=({"recovery_task": task, "job": job},), daemon=True).start()


def run_task(event: dict) -> dict:
    if event["recovery_task"] == "analyze":
        rec = recovery.analyze(event["job"])
        return {"status": rec["status"]}
    return {"error": "unknown task"}


def post_create(event) -> dict:
    try:
        body = _json_body(event)
    except SignupError as e:
        return _resp(e.status, {"error": e.code})
    if not ratelimit.hit("recovery-ip", _source_ip(event), JOBS_PER_IP_PER_HOUR, 3600):
        return _resp(429, {"error": "rate_limited"}, headers={"Retry-After": "3600"})
    if budget.over_budget():
        return _resp(503, {"error": "over_budget"})
    rec = recovery.new_job(str(body.get("lang") or ""), str(body.get("disaster") or "auto"))
    log.info("recovery new job=%s lang=%s disaster=%s", rec["id"][:6], rec["lang"], rec["disaster_choice"])
    return _resp(201, recovery.view(rec))


def post_photo(event, job: str) -> dict:
    raw = event.get("body") or ""
    if len(raw) > MAX_PHOTO_BODY_CHARS:
        return _resp(413, {"error": "photo_too_large"})
    try:
        index = int((event.get("queryStringParameters") or {}).get("i", ""))
    except ValueError:
        return _resp(400, {"error": "too_many_photos"})
    data = base64.b64decode(raw) if event.get("isBase64Encoded") else raw.encode("latin-1")
    return _resp(200, recovery.add_photo(job, index, data))


def post_analyze(job: str) -> dict:
    if budget.over_budget():
        return _resp(503, {"error": "over_budget"})
    rec = recovery.start_analysis(job)
    _start_worker("analyze", job)
    return _resp(202, recovery.view(rec))


def delete_job(job: str) -> dict:
    recovery.load(job)
    recovery.store.delete(job)
    log.info("recovery deleted by person job=%s", job[:6])
    return _resp(200, {"deleted": True})


def handler(event, context):
    if "recovery_task" in event:  # async worker invocation
        return run_task(event)
    route = event.get("routeKey")
    job = (event.get("pathParameters") or {}).get("job", "")
    try:
        if route == "POST /recovery":
            return post_create(event)
        if route == "POST /recovery/{job}/photos":
            return post_photo(event, job)
        if route == "POST /recovery/{job}/analyze":
            return post_analyze(job)
        if route == "GET /recovery/{job}":
            return _resp(200, recovery.view(recovery.load(job)))
        if route == "DELETE /recovery/{job}":
            return delete_job(job)
    except (recovery.JobError, PhotoError) as e:
        return _resp(e.status, {"error": e.code})
    return _resp(404, {"error": "not found"})
