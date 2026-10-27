"""National Weather Service API (free, no key): hourly forecast + active alerts.

Docs: https://www.weather.gov/documentation/services-web-api
"""
from .. import risk
from .http import SourceError, get_json

BASE = "https://api.weather.gov"
_GEOJSON = {"Accept": "application/geo+json"}
_points_cache: dict[tuple, dict] = {}  # lat/lon -> /points properties (stable; cache per container)

ALERT_DESCRIPTION_MAX = 1200  # keep agent prompts small


def _points(lat: float, lon: float) -> dict:
    key = (round(lat, 4), round(lon, 4))
    if key not in _points_cache:
        _points_cache[key] = get_json(f"{BASE}/points/{key[0]},{key[1]}", headers=_GEOJSON)["properties"]
    return _points_cache[key]


def _wind_mph(text: str | None) -> int | None:
    # "5 mph" or "5 to 10 mph" -> upper number
    nums = [int(n) for n in (text or "").replace("mph", "").split() if n.isdigit()]
    return max(nums) if nums else None


def parse_hourly(data: dict, hours: int = 48) -> list[dict]:
    out = []
    for p in data["properties"]["periods"][:hours]:
        temp = p["temperature"]
        if p.get("temperatureUnit") == "C":
            temp = temp * 9 / 5 + 32
        rh = (p.get("relativeHumidity") or {}).get("value")
        out.append({
            "time": p["startTime"],
            "temp_f": round(temp),
            "rh": rh,
            "heat_index_f": round(risk.heat_index_f(temp, rh)) if rh is not None else round(temp),
            "wind_mph": _wind_mph(p.get("windSpeed")),
            "precip_prob": (p.get("probabilityOfPrecipitation") or {}).get("value") or 0,
            "short": p.get("shortForecast"),
        })
    return out


def get_hourly_forecast(lat: float, lon: float, hours: int = 48) -> list[dict]:
    url = _points(lat, lon)["forecastHourly"]
    data = get_json(url, headers=_GEOJSON, timeout=15)
    hourly = parse_hourly(data, hours)
    if not hourly:
        raise SourceError("NWS returned an empty hourly forecast")
    return hourly


def parse_alerts(data: dict) -> list[dict]:
    out = []
    for f in data.get("features", []):
        p = f["properties"]
        if p.get("status") != "Actual" or p.get("messageType") == "Cancel":
            continue
        desc = (p.get("description") or "").strip()
        out.append({
            "id": p["id"],
            "event": p["event"],
            "message_type": p.get("messageType"),  # Alert | Update
            "severity": p.get("severity"),
            "urgency": p.get("urgency"),
            "certainty": p.get("certainty"),
            "headline": p.get("headline"),
            "description": desc[:ALERT_DESCRIPTION_MAX],
            "instruction": (p.get("instruction") or "").strip()[:ALERT_DESCRIPTION_MAX],
            "sent": p.get("sent"),
            "onset": p.get("onset"),
            "ends": p.get("ends"),
            "expires": p.get("expires"),
            "references": [r.get("identifier") for r in p.get("references") or []],
            "sender": p.get("senderName"),
        })
    return out


def get_active_alerts(lat: float, lon: float) -> list[dict]:
    data = get_json(f"{BASE}/alerts/active", params={"point": f"{lat:.4f},{lon:.4f}"}, headers=_GEOJSON)
    return parse_alerts(data)
