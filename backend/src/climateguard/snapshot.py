"""Build one normalized risk snapshot per NWS forecast zone from all data sources.

A snapshot is what the monitoring agent's tools read. Each source can fail
independently; failures land in snapshot["errors"] instead of aborting.

The fingerprint hashes only *material* fields (coarse buckets), so the costly
monitoring agent runs only when the risk picture actually changed — not when
a temperature moves 1F or NWS re-sends the same warning with a new ID.
"""
import hashlib
import json
from datetime import datetime, timedelta, timezone

from . import risk
from .sources import airnow, nws, openmeteo

SUMMARY_HOURS = 24
# Forecasts and AirNow readings update hourly: reuse a fetch younger than this.
REUSE_MINUTES = 45


def _fresh(prev: dict | None, key: str) -> bool:
    ts = (prev or {}).get(key)
    if not ts:
        return False
    return datetime.now(timezone.utc) - datetime.fromisoformat(ts) < timedelta(minutes=REUSE_MINUTES)


def _fetch_forecast(zone: dict):
    try:
        if not zone.get("forecast_hourly"):
            raise RuntimeError("no NWS forecast URL for this zone")
        return "nws", nws.get_hourly_forecast(zone["forecast_hourly"]), None
    except Exception as e:  # NWS is occasionally flaky; fall back rather than go blind
        return "open-meteo", openmeteo.get_hourly_forecast(zone["lat"], zone["lon"], zone["tz"]), f"nws: {e}"


def _fetch_aqi(zone: dict):
    lat, lon, tz = zone["lat"], zone["lon"], zone["tz"]
    if airnow.enabled():
        try:
            return airnow.get_aqi(lat, lon, tz), None
        except Exception as e:
            return openmeteo.get_aqi(lat, lon, tz), f"airnow: {e}"
    return openmeteo.get_aqi(lat, lon, tz), None


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
            "min_temp_f": min(h["temp_f"] for h in window),
            "max_heat_index_f": worst_hi["heat_index_f"],
            "hours_ge_80f": sum(h["temp_f"] >= risk.CALOSHA_SHADE_F for h in window),
            "hours_ge_95f": sum(h["temp_f"] >= risk.CALOSHA_HIGH_HEAT_F for h in window),
            "first_hour_ge_95f": first_95,
            "max_precip_prob": max(h["precip_prob"] for h in window),
            "max_wind_mph": max((h.get("wind_mph") or 0) for h in window),
        })
    cur = (aqi or {}).get("current") or {}
    fc_max = max((f["aqi"] for f in (aqi or {}).get("forecast", []) if f.get("aqi") is not None), default=None)
    s.update({
        "aqi_now": cur.get("aqi"),
        "aqi_category_now": cur.get("category"),
        "pm25_aqi_now": cur.get("pm25_aqi"),
        "aqi_forecast_max": fc_max,
        "active_alerts": sorted({a["event"] for a in alerts}),
        "alert_hazards": sorted({a.get("hazard", "other") for a in alerts}),
    })
    # Threshold markers. The 80F/95F/AQI-151 values are Cal/OSHA rules (California only); outside
    # California they still mark the same physical conditions for the agent and the pre-filter.
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
    """Hash of coarse, decision-relevant fields only (excluded short-fuse warnings are not passed in)."""
    min_t = summary.get("min_temp_f")
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
        # Only cold enough to matter (<= 35F) or windy enough (>= 30 mph) changes these buckets.
        "cold_bucket": max(0, (35 - min_t) // 5 + 1) if min_t is not None and min_t <= 35 else 0,
        "wind_bucket": (summary.get("max_wind_mph") or 0) // 10 if (summary.get("max_wind_mph") or 0) >= 30 else 0,
    }
    blob = json.dumps(material, sort_keys=True, default=list)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def build_snapshot(zone: dict, national_alerts: list[dict] | None, prev: dict | None = None) -> dict:
    """`national_alerts` is the shared nws.get_national_alerts() result (None = alerts source failed)."""
    errors: dict[str, str] = {}
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat(timespec="seconds")

    if _fresh(prev, "forecast_fetched_at") and prev["forecast"]["hours"]:
        fc_source, hours, fc_at = prev["forecast"]["source"], prev["forecast"]["hours"], prev["forecast_fetched_at"]
    else:
        fc_at = now_iso
        try:
            fc_source, hours, warn = _fetch_forecast(zone)
            if warn:
                errors["forecast_primary"] = warn
        except Exception as e:
            fc_source, hours = None, []
            errors["forecast"] = str(e)

    if _fresh(prev, "aqi_fetched_at") and prev.get("aqi"):
        aqi, aqi_at = prev["aqi"], prev["aqi_fetched_at"]
    else:
        aqi_at = now_iso
        try:
            aqi, warn = _fetch_aqi(zone)
            if warn:
                errors["aqi_primary"] = warn
        except Exception as e:
            aqi = None
            errors["aqi"] = str(e)

    if national_alerts is None:
        alerts, excluded = [], []
        errors["alerts"] = "NWS national alerts unavailable"
    else:
        alerts, excluded = nws.alerts_for_zone(national_alerts, zone)

    summary = summarize(hours, aqi, alerts)
    return {
        "zone": zone["zone"],
        "name": zone["name"],
        "place": zone.get("place"),
        "state": zone.get("state"),
        "tz": zone["tz"],
        "demo": bool(zone.get("demo")),
        "generated_at": now_iso,
        "forecast_fetched_at": fc_at,
        "aqi_fetched_at": aqi_at,
        "forecast": {"source": fc_source, "hours": hours},
        "aqi": aqi,
        "alerts": alerts,
        # Short-fuse warnings: stored for transparency, never alerted on (see hazards.py)
        "excluded_alerts": [{"event": a["event"], "ends": a.get("ends") or a.get("expires")} for a in excluded],
        "summary": summary,
        "errors": errors,
        "fingerprint": fingerprint(summary, alerts),
        "stale_after": (now + timedelta(hours=2)).isoformat(timespec="seconds"),
    }
