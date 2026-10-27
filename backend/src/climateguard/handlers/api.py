"""Lambda (HTTP API): read-only city data for the frontend. No model calls.

GET /cities            -> [{slug, name}]
GET /cities/{city}     -> latest snapshot (summary + alerts + hourly forecast + AQI)
"""
import json

from ..cities import CITIES
from ..store import get_store


def _resp(status: int, body) -> dict:
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json", "Cache-Control": "public, max-age=300"},
        "body": json.dumps(body, ensure_ascii=False),
    }


def handler(event, context):
    route = event.get("routeKey", "")
    if route == "GET /cities":
        return _resp(200, [{"slug": s, "name": c["name"]} for s, c in CITIES.items()])
    if route == "GET /cities/{city}":
        city = (event.get("pathParameters") or {}).get("city", "")
        if city not in CITIES:
            return _resp(404, {"error": "unknown city"})
        snap = get_store().get_latest(city)
        if snap is None:
            return _resp(503, {"error": "no data yet, try again in a few minutes"})
        return _resp(200, snap)
    return _resp(404, {"error": "not found"})
