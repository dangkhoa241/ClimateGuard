"""Open-Meteo (free, no key): forecast fallback when NWS is down, and modeled AQI.

Docs: https://open-meteo.com/en/docs, https://open-meteo.com/en/docs/air-quality-api
"""
from datetime import datetime
from zoneinfo import ZoneInfo

from .. import risk
from .http import get_json

def _iso(local: str, tz: ZoneInfo) -> str:
    # Open-Meteo returns naive local times ("2026-10-27T14:00"); make them offset-aware like NWS.
    return datetime.fromisoformat(local).replace(tzinfo=tz).isoformat()


def get_hourly_forecast(lat: float, lon: float, tz_name: str, hours: int = 48) -> list[dict]:
    tz = ZoneInfo(tz_name)
    data = get_json("https://api.open-meteo.com/v1/forecast", params={
        "latitude": lat, "longitude": lon, "timezone": tz_name, "forecast_days": 3,
        "hourly": "temperature_2m,relative_humidity_2m,precipitation_probability,wind_speed_10m",
        "temperature_unit": "fahrenheit", "wind_speed_unit": "mph",
    })
    h = data["hourly"]
    now = datetime.now(tz).replace(minute=0, second=0, microsecond=0)
    out = []
    for i, t in enumerate(h["time"]):
        if datetime.fromisoformat(t).replace(tzinfo=tz) < now:
            continue
        temp, rh = h["temperature_2m"][i], h["relative_humidity_2m"][i]
        out.append({
            "time": _iso(t, tz),
            "temp_f": round(temp),
            "rh": rh,
            "heat_index_f": round(risk.heat_index_f(temp, rh)),
            "wind_mph": round(h["wind_speed_10m"][i]),
            "precip_prob": h["precipitation_probability"][i] or 0,
            "short": None,
        })
        if len(out) == hours:
            break
    return out


def get_aqi(lat: float, lon: float, tz_name: str) -> dict:
    data = get_json("https://air-quality-api.open-meteo.com/v1/air-quality", params={
        "latitude": lat, "longitude": lon, "timezone": tz_name, "forecast_days": 2,
        "current": "us_aqi,us_aqi_pm2_5,us_aqi_ozone",
        "hourly": "us_aqi",
    })
    cur = data["current"]
    pollutant = "PM2.5" if (cur.get("us_aqi_pm2_5") or 0) >= (cur.get("us_aqi_ozone") or 0) else "O3"
    # Daily max of hourly AQI as a simple forecast
    by_day: dict[str, int] = {}
    for t, v in zip(data["hourly"]["time"], data["hourly"]["us_aqi"]):
        if v is not None:
            by_day[t[:10]] = max(by_day.get(t[:10], 0), int(v))
    return {
        "source": "open-meteo",
        "current": {
            "aqi": cur["us_aqi"],
            "category": risk.aqi_category(cur["us_aqi"]),
            "pollutant": pollutant,
            "pm25_aqi": cur.get("us_aqi_pm2_5"),
            "observed_at": _iso(cur["time"], ZoneInfo(tz_name)),
            "area": None,
        },
        "forecast": [{"date": d, "aqi": v, "category": risk.aqi_category(v), "pollutant": None,
                      "action_day": False} for d, v in sorted(by_day.items())],
    }
