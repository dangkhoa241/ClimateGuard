"""EPA AirNow (official monitor readings; free key, ~500 requests/hour).

UNVERIFIED: AirNow's docs are behind a login, so the request format below follows
the commonly used public format. It only runs when AIRNOW_API_KEY is set; verify
with `python scripts/collect_local.py stockton` after adding a key.
"""
from datetime import datetime
from zoneinfo import ZoneInfo

from .. import config, risk
from ..cities import TIMEZONE
from .http import SourceError, get_json

BASE = "https://www.airnowapi.org/aq"
_TZ = ZoneInfo(TIMEZONE)


def _params(lat: float, lon: float, **extra) -> dict:
    return {"format": "application/json", "latitude": lat, "longitude": lon,
            "distance": 25, "API_KEY": config.AIRNOW_API_KEY, **extra}


def get_aqi(lat: float, lon: float) -> dict:
    obs = get_json(f"{BASE}/observation/latLong/current/", params=_params(lat, lon))
    if not obs:
        raise SourceError("AirNow returned no observations within 25 miles")
    worst = max(obs, key=lambda o: o.get("AQI", -1))
    pm25 = next((o["AQI"] for o in obs if o.get("ParameterName") == "PM2.5"), None)
    observed = datetime.strptime(worst["DateObserved"].strip(), "%Y-%m-%d").replace(
        hour=int(worst.get("HourObserved", 0)), tzinfo=_TZ)

    today = datetime.now(_TZ).strftime("%Y-%m-%d")
    fc_raw = get_json(f"{BASE}/forecast/latLong/", params=_params(lat, lon, date=today))
    by_day: dict[str, dict] = {}
    for f in fc_raw:
        day = f["DateForecast"].strip()
        aqi = f.get("AQI", -1)
        cat_num = (f.get("Category") or {}).get("Number", 0)
        prev = by_day.get(day)
        if prev is None or cat_num > prev["_cat"]:
            by_day[day] = {"date": day, "aqi": aqi if aqi >= 0 else None,
                           "category": (f.get("Category") or {}).get("Name"),
                           "pollutant": f.get("ParameterName"),
                           "action_day": bool(f.get("ActionDay")), "_cat": cat_num}

    return {
        "source": "airnow",
        "current": {
            "aqi": worst["AQI"],
            "category": (worst.get("Category") or {}).get("Name") or risk.aqi_category(worst["AQI"]),
            "pollutant": worst.get("ParameterName"),
            "pm25_aqi": pm25,
            "observed_at": observed.isoformat(),
            "area": worst.get("ReportingArea"),
        },
        "forecast": [{k: v for k, v in d.items() if k != "_cat"} for _, d in sorted(by_day.items())],
    }
