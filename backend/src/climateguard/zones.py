"""NWS forecast zones: the unit ClimateGuard monitors and alerts.

A location (ZIP or browser coordinates) maps to its NWS forecast zone through the
points API. One agent run per zone covers every subscriber in it.

Registry record (one per zone; local JSON file or ZONES_TABLE):
  zone, name, state, county, fire_zone, tz, office, lat, lon, place, forecast_hourly,
  demo, langs (languages with sign-ups), confirmed (confirmed subscriptions),
  confirmed_checked_at
Data is collected only for zones with confirmed > 0, plus the demo zones.
"""
import json
import time

from . import config, geo
from .sources.http import SourceError, get_json

NWS = "https://api.weather.gov"
_GEOJSON = {"Accept": "application/geo+json"}

# Demo focus (fixed, so demos and tests never depend on the network). Values from the NWS
# points API, checked 2026-10-27. Zone numbers changed in 2025: Stockton was CAZ019 in 2022.
DEMO_ZONES = {
    "CAZ159": {"zone": "CAZ159", "name": "Central San Joaquin County Including Stockton Metro", "state": "CA",
               "county": "CAC077", "fire_zone": "CAZ159", "tz": "America/Los_Angeles", "office": "STO",
               "lat": 37.9597, "lon": -121.2883, "place": "Stockton, CA",
               "forecast_hourly": f"{NWS}/gridpoints/STO/43,39/forecast/hourly", "demo": True},
    "CAZ303": {"zone": "CAZ303", "name": "Planada - Le Grand - Snelling", "state": "CA",
               "county": "CAC047", "fire_zone": "CAZ580", "tz": "America/Los_Angeles", "office": "HNX",
               "lat": 37.3012, "lon": -120.3315, "place": "Planada, CA",
               "forecast_hourly": f"{NWS}/gridpoints/HNX/37,128/forecast/hourly", "demo": True},
}


class ZoneError(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _last(url: str | None) -> str | None:
    return url.rstrip("/").rsplit("/", 1)[-1] if url else None


def resolve_point(lat: float, lon: float) -> dict:
    """NWS points API -> zone record (not yet registered). Network call; cache the result."""
    try:
        p = get_json(f"{NWS}/points/{lat:.4f},{lon:.4f}", headers=_GEOJSON)["properties"]
    except SourceError as e:
        if "404" in str(e):
            raise ZoneError("not_covered") from None  # outside NWS coverage
        raise ZoneError("nws_unavailable") from None
    zone = _last(p.get("forecastZone"))
    if not zone:
        raise ZoneError("not_covered")
    rel = (p.get("relativeLocation") or {}).get("properties") or {}
    name = zone
    try:
        name = get_json(f"{NWS}/zones/forecast/{zone}", headers=_GEOJSON)["properties"]["name"]
    except Exception:
        pass  # the name is cosmetic
    return {"zone": zone, "name": name, "state": rel.get("state") or zone[:2], "county": _last(p.get("county")),
            "fire_zone": _last(p.get("fireWeatherZone")), "tz": p.get("timeZone") or "America/New_York",
            "office": p.get("gridId"), "lat": round(lat, 4), "lon": round(lon, 4),
            "place": ", ".join(x for x in (rel.get("city"), rel.get("state")) if x) or name,
            "forecast_hourly": p.get("forecastHourly"), "demo": False}


# --- registry ----------------------------------------------------------------

def _table():
    import boto3

    return boto3.resource("dynamodb").Table(config.ZONES_TABLE)


def _local_path():
    return config.LOCAL_DIR / "zones.json"


def _load_local() -> dict:
    p = _local_path()
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def get(zone: str) -> dict | None:
    zone = (zone or "").upper()
    if config.STORAGE == "dynamodb":
        item = _table().get_item(Key={"zone": zone}).get("Item")
        rec = json.loads(item["body"]) if item else None
    else:
        rec = _load_local().get(zone)
    if rec is None and zone in DEMO_ZONES:
        rec = dict(DEMO_ZONES[zone], langs=[], confirmed=0)
    return rec


def put(rec: dict) -> dict:
    rec = {**rec, "updated_at": int(time.time())}
    if config.STORAGE == "dynamodb":
        _table().put_item(Item={"zone": rec["zone"], "body": json.dumps(rec, ensure_ascii=False)})
    else:
        data = _load_local()
        data[rec["zone"]] = rec
        _local_path().parent.mkdir(parents=True, exist_ok=True)
        _local_path().write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    return rec


def all_zones() -> list[dict]:
    if config.STORAGE == "dynamodb":
        table, kwargs, out = _table(), {}, []
        while True:
            page = table.scan(**kwargs)
            out += [json.loads(i["body"]) for i in page["Items"]]
            if "LastEvaluatedKey" not in page:
                break
            kwargs["ExclusiveStartKey"] = page["LastEvaluatedKey"]
        recs = {r["zone"]: r for r in out}
    else:
        recs = _load_local()
    for z, demo in DEMO_ZONES.items():
        recs.setdefault(z, dict(demo, langs=[], confirmed=0))
    return list(recs.values())


def monitored() -> list[dict]:
    """Zones to collect and run the agent for: confirmed subscribers, plus the demo zones."""
    return [z for z in all_zones() if z.get("demo") or (z.get("confirmed") or 0) > 0]


def locate(zip_code: str | None = None, lat=None, lon=None) -> dict:
    """ZIP or coordinates -> registered zone record (registers it on first use)."""
    if zip_code:
        lat, lon = geo.zip_to_point(zip_code)
    else:
        lat, lon = geo.coarse_point(lat, lon)
    for demo in DEMO_ZONES.values():  # no network for the demo area
        if abs(demo["lat"] - lat) < 0.02 and abs(demo["lon"] - lon) < 0.02:
            return get(demo["zone"])
    resolved = resolve_point(lat, lon)
    existing = get(resolved["zone"])
    if existing:
        return existing
    return put({**resolved, "langs": [], "confirmed": 0})


def add_language(zone: str, lang: str) -> dict:
    rec = get(zone)
    if rec is None:
        raise ZoneError("unknown_zone")
    if lang not in rec.get("langs", []):
        rec = put({**rec, "langs": sorted(set(rec.get("langs", [])) | {lang})})
    return rec
