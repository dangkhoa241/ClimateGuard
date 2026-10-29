"""Lambda (HTTP API): public endpoints for the frontend. No model calls.

GET  /locate?zip=95202 | ?lat=..&lon=..  -> the NWS forecast zone for a location
GET  /zones/{zone}                       -> latest snapshot (summary + alerts + hourly forecast + AQI)
GET  /zones/{zone}/alerts                -> alerts ClimateGuard sent to this zone in the last 48 h
POST /subscribe                          -> {email, lang, zip | lat+lon} sign-up (SNS double opt-in)
GET  /decisions?zone=&days=7&limit=50    -> the live agent's real decisions + daily counters (public)
GET  /demo                               -> demo mode: replay buttons, real model cost so far, budget state
"""
import base64
import json
import logging
import re

from .. import alerts_store, budget, demo, hazards, ratelimit, stats, zones
from ..geo import GeoError
from ..languages import LANGS
from ..store import get_store
from ..subscriptions import SignupError, subscribe

log = logging.getLogger()
MAX_BODY_BYTES = 2048
ZONE_RE = re.compile(r"^[A-Z]{2}Z\d{3}$")
LOCATE_PER_IP_PER_HOUR = 30  # a lookup can cost two NWS requests


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


def _zone_view(rec: dict) -> dict:
    return {"zone": rec["zone"], "name": rec["name"], "place": rec.get("place"), "state": rec.get("state"),
            "tz": rec.get("tz"), "demo": bool(rec.get("demo")),
            "monitored": bool(rec.get("demo") or (rec.get("confirmed") or 0) > 0),
            "calosha_applies": rec.get("state") == "CA", "not_covered": hazards.EXCLUSION_NOTE}


def get_locate(event) -> dict:
    q = event.get("queryStringParameters") or {}
    if not ratelimit.hit("locate-ip", _source_ip(event), LOCATE_PER_IP_PER_HOUR, 3600):
        return _resp(429, {"error": "rate_limited"}, headers={"Retry-After": "3600"})
    try:
        rec = zones.locate(zip_code=q.get("zip"), lat=q.get("lat"), lon=q.get("lon")) if (
            q.get("zip") or (q.get("lat") and q.get("lon"))) else None
    except GeoError as e:
        return _resp(400, {"error": e.code})
    except zones.ZoneError as e:
        return _resp(503 if e.code == "nws_unavailable" else 400, {"error": e.code})
    if rec is None:
        return _resp(400, {"error": "missing_location"})
    return _resp(200, _zone_view(rec), cache_s=3600)


def post_subscribe(event) -> dict:
    try:
        body = _json_body(event)
        if body.get("website"):  # honeypot field, hidden from humans: pretend success, do nothing
            return _resp(202, {"status": "pending_confirmation"})
        result = subscribe(str(body.get("email", "")), str(body.get("lang", "")), ip=_source_ip(event),
                           zip_code=body.get("zip"), lat=body.get("lat"), lon=body.get("lon"))
        return _resp(202, {**result, "not_covered": hazards.EXCLUSION_NOTE})
    except SignupError as e:
        headers = {"Retry-After": "3600"} if e.status == 429 else None
        return _resp(e.status, {"error": e.code}, headers=headers)


def get_zone_alerts(zone: str) -> dict:
    rows = alerts_store.recent_sent(zone, hours=48)
    rows.sort(key=lambda r: r["ts"], reverse=True)
    return _resp(200, [{"sent_at": r["ts"], "hazard": r["hazard"], "severity": r["severity"],
                        "messages": r["messages"]} for r in rows], cache_s=60)


def _public_decision(zone: dict, d: dict) -> dict:
    """What the public history shows for one decision (no internal ids or raw tool payloads)."""
    return {"ts": d["ts"], "zone": d["zone"], "place": zone.get("place") or zone.get("name"),
            "action": d["action"], "reason": d["reason"], "signals": d.get("signals") or [],
            "tools": [{"tool": t["tool"], **({"rejected": t["rejected"]} if t.get("rejected") else {})}
                      for t in d.get("tools") or []],
            "alerts": [{"hazard": s["hazard"], "severity": s["severity"], "messages": s["messages"]}
                       for s in d.get("sent") or []],
            "model_calls": int(d.get("model_calls") or 0), "cost_usd": round(float(d.get("cost_usd") or 0), 4)}


def get_decisions(event) -> dict:
    """Live decisions only: replays/evals live in REPLAY-*/EVAL-* namespaces, never under a zone id."""
    q = event.get("queryStringParameters") or {}
    try:
        days = min(max(int(q.get("days", 7)), 1), 30)
        limit = min(max(int(q.get("limit", 50)), 1), 200)
    except ValueError:
        return _resp(400, {"error": "invalid_query"})
    wanted = (q.get("zone") or "").upper()
    if wanted and not ZONE_RE.match(wanted):
        return _resp(404, {"error": "unknown_zone"})
    zone_list = [z for z in zones.monitored() if not wanted or z["zone"] == wanted]
    rows = []
    for z in zone_list:
        rows += [_public_decision(z, d) for d in alerts_store.recent_decisions(z["zone"], hours=days * 24)
                 if not d.get("replay")]
    rows.sort(key=lambda r: r["ts"], reverse=True)
    daily = stats.recent(days)
    return _resp(200, {"days": days, "since": min((r["day"] for r in daily), default=None),
                       "totals": stats.totals(daily), "by_day": daily,
                       "zones": [{"zone": z["zone"], "place": z.get("place"), "demo": bool(z.get("demo"))}
                                 for z in zone_list],
                       "decisions": rows[:limit]}, cache_s=60)


def get_demo() -> dict:
    """Demo mode's setup: the replay buttons, the deployed app's real model cost, and whether today's
    budget is spent (then replays show earlier saved runs). Reads the usage log, so cached."""
    try:
        cost, spent = demo.cost_so_far(), budget.over_budget()
    except Exception as e:  # usage log unreadable: the demo still works, without the cost line
        log.warning("demo cost unavailable: %s", e)
        cost, spent = None, False
    return _resp(200, {"events": demo.catalog(), "cost": cost, "over_budget": spent}, cache_s=300)


def handler(event, context):
    route = event.get("routeKey", "")
    if route == "GET /decisions":
        return get_decisions(event)
    if route == "GET /demo":
        return get_demo()
    zone = ((event.get("pathParameters") or {}).get("zone") or "").upper()
    if route == "GET /locate":
        return get_locate(event)
    if route == "GET /languages":
        return _resp(200, LANGS, cache_s=86400)
    if route == "POST /subscribe":
        return post_subscribe(event)
    if route in ("GET /zones/{zone}", "GET /zones/{zone}/alerts") and not ZONE_RE.match(zone):
        return _resp(404, {"error": "unknown_zone"})
    if route == "GET /zones/{zone}":
        snap = get_store().get_latest(zone)
        if snap is None:
            rec = zones.get(zone)
            code = "not_monitored" if rec else "unknown_zone"  # monitored once someone confirms a sign-up
            return _resp(404, {"error": code, **({"zone": _zone_view(rec)} if rec else {})})
        return _resp(200, snap, cache_s=300)
    if route == "GET /zones/{zone}/alerts":
        return get_zone_alerts(zone)
    return _resp(404, {"error": "not found"})
