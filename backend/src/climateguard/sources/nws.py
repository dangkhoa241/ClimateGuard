"""National Weather Service API (free, no key): hourly forecast + active alerts.

Docs: https://www.weather.gov/documentation/services-web-api

Alerts are fetched ONCE per collector run for the whole country (~300 alerts, ~1.4 MB)
and matched to each monitored zone by UGC code (forecast zone, county, fire zone),
instead of one request per zone.
"""
from .. import hazards, risk
from .http import SourceError, get_json

BASE = "https://api.weather.gov"
_GEOJSON = {"Accept": "application/geo+json"}

ALERT_DESCRIPTION_MAX = 1200  # keep agent prompts small


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


def get_hourly_forecast(forecast_url: str, hours: int = 48) -> list[dict]:
    data = get_json(forecast_url, headers=_GEOJSON, timeout=15)
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
            "hazard": hazards.group_for(p["event"]),
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
            "ugc": sorted(set(((p.get("geocode") or {}).get("UGC")) or [])),
        })
    return out


def get_national_alerts() -> list[dict]:
    """Every active, actual US alert in one request."""
    return parse_alerts(get_json(f"{BASE}/alerts/active", params={"status": "actual"},
                                 headers=_GEOJSON, timeout=20))


def get_zone_alerts(zone: dict) -> list[dict]:
    """Active alerts for one zone's forecast zone, county and fire zone (for an on-demand snapshot,
    e.g. a question from a place nobody has subscribed to yet). Same shape as the national list."""
    codes = ",".join(c for c in (zone.get("zone"), zone.get("county"), zone.get("fire_zone")) if c)
    return parse_alerts(get_json(f"{BASE}/alerts/active", params={"status": "actual", "zone": codes},
                                 headers=_GEOJSON, timeout=10))


def alerts_for_zone(alerts: list[dict], zone: dict) -> tuple[list[dict], list[dict]]:
    """Alerts covering this zone, split into (handled, excluded short-fuse warnings)."""
    codes = {c for c in (zone.get("zone"), zone.get("county"), zone.get("fire_zone")) if c}
    mine = [a for a in alerts if codes & set(a.get("ugc", []))]
    return ([a for a in mine if not hazards.is_excluded(a["event"])],
            [a for a in mine if hazards.is_excluded(a["event"])])
