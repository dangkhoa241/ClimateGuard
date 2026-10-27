"""Build one normalized risk snapshot per city from all data sources.

A snapshot is what the monitoring agent's tools read. Each source can fail
independently; failures land in snapshot["errors"] instead of aborting.

The fingerprint hashes only *material* fields (coarse buckets), so the costly
monitoring agent runs only when the risk picture actually changed — not when
a temperature moves 1F or NWS re-sends the same warning with a new ID.
"""
import hashlib
import json
from datetime import datetime, timedelta, timezone

from . import config, risk
from .cities import get_city
from .sources import airnow, nws, openmeteo

SUMMARY_HOURS = 24


def _fetch_forecast(lat, lon):
    try:
        return "nws", nws.get_hourly_forecast(lat, lon), None
    except Exception as e:  # NWS is occasionally flaky; fall back rather than go blind
        return "open-meteo", openmeteo.get_hourly_forecast(lat, lon), f"nws: {e}"


def _fetch_aqi(lat, lon):
    if config.AIRNOW_API_KEY:
        try:
            return airnow.get_aqi(lat, lon), None
        except Exception as e:
            return openmeteo.get_aqi(lat, lon), f"airnow: {e}"
    return openmeteo.get_aqi(lat, lon), None


def summarize(hours: list[dict], aqi: dict | None, alerts: list[dict]) -> dict:
    window = hours[:SUMMARY_HOURS]
    s: dict = {"hours_covered": len(window)}
    if window:
        hottest = max(window, key=lambda h: h["temp_f"])
        worst_hi = max(window, key=lambda h: h["heat_index_f"])
        first_95 = next((h["time"] for h in window if h["temp_f"] >= risk.CALOSHA_HIGH_HEAT_F), None)
        s.update({
            "max_temp_f": hottest["temp_f"],
            "max_temp_time": hottest["time"],
            "max_heat_index_f": worst_hi["heat_index_f"],
            "hours_ge_80f": sum(h["temp_f"] >= risk.CALOSHA_SHADE_F for h in window),
            "hours_ge_95f": sum(h["temp_f"] >= risk.CALOSHA_HIGH_HEAT_F for h in window),
            "first_hour_ge_95f": first_95,
            "max_precip_prob": max(h["precip_prob"] for h in window),
        })
    cur = (aqi or {}).get("current") or {}
    fc_max = max((f["aqi"] for f in (aqi or {}).get("forecast", []) if f.get("aqi") is not None), default=None)
    s.update({
        "aqi_now": cur.get("aqi"),
        "aqi_category_now": cur.get("category"),
        "pm25_aqi_now": cur.get("pm25_aqi"),
        "aqi_forecast_max": fc_max,
        "active_alerts": sorted({a["event"] for a in alerts}),
    })
    flags = []
    if s.get("hours_ge_80f"):
        flags.append("calosha_shade_80f")
    if s.get("hours_ge_95f"):
        flags.append("calosha_high_heat_95f")
    if max(cur.get("pm25_aqi") or 0, fc_max or 0) >= risk.CALOSHA_SMOKE_AQI:
        flags.append("calosha_smoke_aqi_151")
    if alerts:
        flags.append("nws_alert_active")
    s["flags"] = flags
    return s


def fingerprint(summary: dict, alerts: list[dict]) -> str:
    """Hash of coarse, decision-relevant fields only."""
    material = {
        # Re-issued NWS alerts get new IDs and sent-times; identify by what matters instead.
        "alerts": sorted({(a["event"], a.get("severity"), (a.get("ends") or a.get("expires") or "")[:13])
                          for a in alerts}),
        "max_temp_5f": (summary.get("max_temp_f") or 0) // 5,
        "max_hi_5f": (summary.get("max_heat_index_f") or 0) // 5,
        "hot_hours_bucket": min((summary.get("hours_ge_95f") or 0) // 3, 4),
        "precip_bucket": (summary.get("max_precip_prob") or 0) // 25,
        "aqi_cat_now": risk.aqi_category_index(summary.get("aqi_now")),
        "aqi_cat_fc": risk.aqi_category_index(summary.get("aqi_forecast_max")),
        "flags": summary.get("flags", []),
    }
    blob = json.dumps(material, sort_keys=True, default=list)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def build_snapshot(slug: str) -> dict:
    city = get_city(slug)
    lat, lon = city["lat"], city["lon"]
    errors: dict[str, str] = {}

    try:
        fc_source, hours, warn = _fetch_forecast(lat, lon)
        if warn:
            errors["forecast_primary"] = warn
    except Exception as e:
        fc_source, hours = None, []
        errors["forecast"] = str(e)

    try:
        aqi, warn = _fetch_aqi(lat, lon)
        if warn:
            errors["aqi_primary"] = warn
    except Exception as e:
        aqi = None
        errors["aqi"] = str(e)

    try:
        alerts = nws.get_active_alerts(lat, lon)
    except Exception as e:
        alerts = []
        errors["alerts"] = str(e)

    summary = summarize(hours, aqi, alerts)
    now = datetime.now(timezone.utc)
    return {
        "city": slug,
        "name": city["name"],
        "generated_at": now.isoformat(timespec="seconds"),
        "forecast": {"source": fc_source, "hours": hours},
        "aqi": aqi,
        "alerts": alerts,
        "summary": summary,
        "errors": errors,
        "fingerprint": fingerprint(summary, alerts),
        "stale_after": (now + timedelta(hours=2)).isoformat(timespec="seconds"),
    }
