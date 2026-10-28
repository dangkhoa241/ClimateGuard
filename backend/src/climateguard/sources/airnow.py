"""EPA AirNow (official monitor readings; free key).

AirNow retired its old lat/long web services on 2026-10-01 (they now return 410).
This uses the replacement services; field names verified against live responses
on 2026-10-27 (AirNow's own docs are behind a login):
  observations: /aq/observation/current/ziplatlong/  -> dateObserved, hourObserved ("2:00"),
                parameterName (PM2.5 | OZONE | PM10), nowcastAQI, aqiCategoryName, reportingAreaName
  forecasts:    /aq/forecast/current/                -> dateValid, parameterName, aqi (-1 if none),
                categoryNumber, categoryName, actionDay, discussion
"""
from datetime import datetime
from zoneinfo import ZoneInfo

from .. import config, risk, ssm
from .http import SourceError, get_json

BASE = "https://www.airnowapi.org/aq"
_POLLUTANT = {"OZONE": "O3"}  # keep the short names used elsewhere


def enabled() -> bool:
    return bool(config.AIRNOW_API_KEY or config.AIRNOW_API_KEY_PARAM)


def _api_key() -> str:
    return config.AIRNOW_API_KEY or ssm.get_secret(config.AIRNOW_API_KEY_PARAM)


def _params(lat: float, lon: float) -> dict:
    return {"format": "application/json", "latitude": lat, "longitude": lon,
            "distance": 25, "API_KEY": _api_key()}


def parse_observations(obs: list, tz_name: str = "America/Los_Angeles") -> dict:
    readings = [o for o in obs if isinstance(o.get("nowcastAQI"), int) and o["nowcastAQI"] >= 0]
    if not readings:
        raise SourceError("AirNow returned no observations within 25 miles")
    worst = max(readings, key=lambda o: o["nowcastAQI"])
    pm25 = next((o["nowcastAQI"] for o in readings if o.get("parameterName") == "PM2.5"), None)
    pm10 = next((o["nowcastAQI"] for o in readings if o.get("parameterName") == "PM10"), None)
    hour = int(str(worst.get("hourObserved", "0")).split(":")[0])
    observed = datetime.strptime(worst["dateObserved"].strip(), "%Y-%m-%d").replace(hour=hour, tzinfo=ZoneInfo(tz_name))
    return {
        "aqi": worst["nowcastAQI"],
        "category": worst.get("aqiCategoryName") or risk.aqi_category(worst["nowcastAQI"]),
        "pollutant": _POLLUTANT.get(worst.get("parameterName"), worst.get("parameterName")),
        "pm25_aqi": pm25,
        "pm10_aqi": pm10,
        "observed_at": observed.isoformat(),
        "area": worst.get("reportingAreaName"),
    }


_PARTICLES = ("PM2.5", "PM10")
UNHEALTHY_FOR_SENSITIVE_CATEGORY = 3


def parse_forecast(rows: list) -> list[dict]:
    """One entry per day for the worst pollutant. `particles_unhealthy` is kept separately, because
    on a day with both ozone and smoke the worst pollutant may be ozone, and masks still help with smoke."""
    by_day: dict[str, dict] = {}
    particles: dict[str, bool] = {}
    for f in rows:
        day = (f.get("dateValid") or "").strip()
        if not day:
            continue
        aqi = f.get("aqi")
        aqi = aqi if isinstance(aqi, int) and aqi >= 0 else None
        cat_num = f.get("categoryNumber") or 0
        if f.get("parameterName") in _PARTICLES and (cat_num >= UNHEALTHY_FOR_SENSITIVE_CATEGORY or (aqi or 0) >= 101):
            particles[day] = True
        prev = by_day.get(day)
        if prev is None or cat_num > prev["_cat"] or (cat_num == prev["_cat"] and (aqi or 0) > (prev["aqi"] or 0)):
            by_day[day] = {"date": day, "aqi": aqi, "category": f.get("categoryName") or risk.aqi_category(aqi),
                           "pollutant": _POLLUTANT.get(f.get("parameterName"), f.get("parameterName")),
                           "action_day": bool(f.get("actionDay")), "_cat": cat_num}
    return [{**{k: v for k, v in d.items() if k != "_cat"}, "particles_unhealthy": particles.get(day, False)}
            for day, d in sorted(by_day.items())]


def get_aqi(lat: float, lon: float, tz_name: str) -> dict:
    current = parse_observations(get_json(f"{BASE}/observation/current/ziplatlong/", params=_params(lat, lon)),
                                 tz_name)
    try:
        forecast = parse_forecast(get_json(f"{BASE}/forecast/current/", params=_params(lat, lon)))
    except SourceError:
        forecast = []  # forecasts are optional; current readings are what matter most
    return {"source": "airnow", "current": current, "forecast": forecast}
