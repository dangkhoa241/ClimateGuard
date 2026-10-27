"""Lambda (HTTP API): public endpoints for the frontend. No model calls.

GET  /cities                 -> [{slug, name}]
GET  /cities/{city}          -> latest snapshot (summary + alerts + hourly forecast + AQI)
GET  /cities/{city}/alerts   -> alerts ClimateGuard sent to this city in the last 48 h
POST /subscribe              -> {email, city, lang} sign-up for email alerts (double opt-in)
"""
import base64
import json
import logging

from .. import alerts_store
from ..cities import CITIES
from ..store import get_store
from ..subscriptions import SignupError, subscribe

log = logging.getLogger()
MAX_BODY_BYTES = 2048


def _resp(status: int, body, cache_s: int = 0, headers: dict | None = None) -> dict:
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json",
                    "Cache-Control": f"public, max-age={cache_s}" if cache_s else "no-store",
                    **(headers or {})},
        "body": json.dumps(body, ensure_ascii=False),
    }


def _json_body(event) -> dict:
    raw = event.get("body") or ""
    if event.get("isBase64Encoded"):
        raw = base64.b64decode(raw).decode("utf-8", "replace")
    if len(raw) > MAX_BODY_BYTES:
        raise SignupError("too_large", 413)
    try:
        body = json.loads(raw or "{}")
    except json.JSONDecodeError:
        raise SignupError("invalid_json", 400) from None
    if not isinstance(body, dict):
        raise SignupError("invalid_json", 400)
    return body


def _source_ip(event) -> str:
    return ((event.get("requestContext") or {}).get("http") or {}).get("sourceIp", "unknown")


def post_subscribe(event) -> dict:
    try:
        body = _json_body(event)
        if body.get("website"):  # honeypot field, hidden from humans: pretend success, do nothing
            return _resp(202, {"status": "pending_confirmation"})
        result = subscribe(str(body.get("email", "")), str(body.get("city", "")), str(body.get("lang", "")),
                           ip=_source_ip(event))
        return _resp(202, result)
    except SignupError as e:
        headers = {"Retry-After": "3600"} if e.status == 429 else None
        return _resp(e.status, {"error": e.code}, headers=headers)


def get_city_alerts(city: str) -> dict:
    rows = alerts_store.recent_sent(city, hours=48)
    rows.sort(key=lambda r: r["ts"], reverse=True)
    return _resp(200, [{"sent_at": r["ts"], "hazard": r["hazard"], "severity": r["severity"],
                        "messages": r["messages"]} for r in rows], cache_s=60)


def handler(event, context):
    route = event.get("routeKey", "")
    city = (event.get("pathParameters") or {}).get("city", "")
    if route == "GET /cities":
        return _resp(200, [{"slug": s, "name": c["name"]} for s, c in CITIES.items()], cache_s=3600)
    if route == "POST /subscribe":
        return post_subscribe(event)
    if route in ("GET /cities/{city}", "GET /cities/{city}/alerts") and city not in CITIES:
        return _resp(404, {"error": "unknown city"})
    if route == "GET /cities/{city}":
        snap = get_store().get_latest(city)
        if snap is None:
            return _resp(503, {"error": "no data yet, try again in a few minutes"})
        return _resp(200, snap, cache_s=300)
    if route == "GET /cities/{city}/alerts":
        return get_city_alerts(city)
    return _resp(404, {"error": "not found"})
