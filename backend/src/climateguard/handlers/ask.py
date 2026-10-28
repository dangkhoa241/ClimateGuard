"""Lambda (HTTP API): POST /ask {question, lang, zone} -> an answer in the person's language.

Its own function (not api.py) because it calls a model: longer timeout, model-key access.
Per-IP rate limit; the daily model budget is checked in ask.answer().
"""
import logging

from .. import ask, llm, ratelimit
from ..languages import LANGS
from ..subscriptions import SignupError
from .api import ZONE_RE, _json_body, _resp, _source_ip

log = logging.getLogger()
ASK_PER_IP_PER_HOUR = 20

# Cold start: create the model client (OpenAI SDK import + API key from SSM) during Lambda init,
# which runs once per instance with a full CPU, instead of inside the first person's request.
try:
    llm._client("meta")
except Exception as e:  # no key yet, SSM down...: the request path retries and falls back
    log.warning("model client not ready at init: %s", e)


def post_ask(event) -> dict:
    try:
        body = _json_body(event)
    except SignupError as e:
        return _resp(e.status, {"error": e.code})
    question = str(body.get("question") or "").strip()
    lang = str(body.get("lang") or "")
    zone = str(body.get("zone") or "").upper()
    if not question or len(question) > ask.MAX_QUESTION_CHARS:
        return _resp(400, {"error": "invalid_question"})
    if lang not in LANGS:
        return _resp(400, {"error": "invalid_lang"})
    if not ZONE_RE.match(zone):
        return _resp(400, {"error": "unknown_zone"})
    if not ratelimit.hit("ask-ip", _source_ip(event), ASK_PER_IP_PER_HOUR, 3600):
        return _resp(429, {"error": "rate_limited"}, headers={"Retry-After": "3600"})
    result = ask.answer(question, lang, zone)
    log.info("ask zone=%s lang=%s kind=%s blocked=%s", zone, lang, result["kind"], result.get("blocked"))
    return _resp(200, result)


def handler(event, context):
    if event.get("routeKey") == "POST /ask":
        return post_ask(event)
    return _resp(404, {"error": "not found"})
