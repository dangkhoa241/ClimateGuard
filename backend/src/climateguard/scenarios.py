"""Synthetic snapshots for testing the monitoring agent.

Shapes match snapshot.build_snapshot(); times start at the current hour in the zone's
timezone so the agent sees a plausible "now". (Real archived events come in replays.)
"""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from . import hazards, risk, snapshot, zones

# A non-California zone for testing other timezones and hazards (not monitored, test data only)
TEST_ZONES = {
    "MNZ060": {"zone": "MNZ060", "name": "Hennepin", "state": "MN", "tz": "America/Chicago",
               "place": "Minneapolis, MN", "county": "MNC053", "fire_zone": "MNZ060", "lat": 44.98, "lon": -93.27},
    "FLZ173": {"zone": "FLZ173", "name": "Coastal Miami Dade County", "state": "FL", "tz": "America/New_York",
               "place": "Miami, FL", "county": "FLC086", "fire_zone": "FLZ173", "lat": 25.77, "lon": -80.19},
}


def _zone(zone_id: str) -> dict:
    return zones.DEMO_ZONES.get(zone_id) or TEST_ZONES[zone_id]


def _hours(tz, temp_at, rh_at, precip_at=lambda h: 0, short_at=lambda h: "Sunny", wind_at=lambda h: 8, n=48):
    start = datetime.now(tz).replace(minute=0, second=0, microsecond=0)
    out = []
    for i in range(n):
        t = start + timedelta(hours=i)
        temp, rh = temp_at(t.hour), rh_at(t.hour)
        out.append({"time": t.isoformat(), "temp_f": temp, "rh": rh,
                    "heat_index_f": round(risk.heat_index_f(temp, rh)), "wind_mph": wind_at(t.hour),
                    "precip_prob": precip_at(t.hour), "short": short_at(t.hour)})
    return out


def _aqi(tz, now, fc, pollutant="PM2.5"):
    today = datetime.now(tz).date()
    return {"source": "scenario",
            "current": {"aqi": now, "category": risk.aqi_category(now), "pollutant": pollutant,
                        "pm25_aqi": now if pollutant == "PM2.5" else None,
                        "observed_at": datetime.now(tz).isoformat(timespec="seconds"), "area": None},
            "forecast": [{"date": str(today + timedelta(days=d)), "aqi": v, "category": risk.aqi_category(v),
                          "pollutant": pollutant, "action_day": v > 100} for d, v in enumerate(fc)]}


def _nws(tz, event, severity, hours_from_now, headline, description, instruction, sender="NWS Sacramento CA"):
    now = datetime.now(tz)
    ends = (now + timedelta(hours=hours_from_now)).isoformat(timespec="seconds")
    return {"id": f"scenario-{event.lower().replace(' ', '-')}", "event": event, "hazard": hazards.group_for(event),
            "message_type": "Alert", "severity": severity, "urgency": "Expected", "certainty": "Likely",
            "headline": headline, "description": description, "instruction": instruction,
            "sent": now.isoformat(timespec="seconds"), "onset": now.isoformat(timespec="seconds"),
            "ends": ends, "expires": ends, "references": [], "sender": sender, "ugc": []}


def _heat_curve(peak):
    # cool nights, peak at 4 PM
    return lambda h: round(peak - 30 + 30 * max(0.0, 1 - abs(h - 16) / 9))


SCENARIOS = {
    "heatwave": ("CAZ159", lambda tz: dict(
        hours=_hours(tz, _heat_curve(108), lambda h: 22 if 10 <= h <= 20 else 45),
        aqi=_aqi(tz, 72, [78, 80]),
        alerts=[_nws(tz, "Extreme Heat Warning", "Severe", 36,
                     "Extreme Heat Warning in effect through tomorrow evening",
                     "Dangerously hot conditions with temperatures up to 108 expected.",
                     "Drink plenty of fluids, stay in an air-conditioned room, stay out of the sun.")])),
    "smoke": ("CAZ159", lambda tz: dict(
        hours=_hours(tz, _heat_curve(88), lambda h: 30, short_at=lambda h: "Areas of Smoke"),
        aqi=_aqi(tz, 178, [185, 160]),
        alerts=[_nws(tz, "Air Quality Alert", "Unknown", 30, "Air Quality Alert due to wildfire smoke",
                     "Smoke from a wildfire will cause unhealthy air quality.",
                     "Limit time outdoors. Keep windows and doors closed.")])),
    "flood": ("CAZ303", lambda tz: dict(
        hours=_hours(tz, lambda h: 52, lambda h: 95, precip_at=lambda h: 90, short_at=lambda h: "Heavy Rain"),
        aqi=_aqi(tz, 25, [20, 22]),
        alerts=[_nws(tz, "Flood Warning", "Severe", 24, "Flood Warning for Bear Creek near Planada",
                     "Heavy rain is causing flooding of low-lying areas and roads.",
                     "Turn around, don't drown when encountering flooded roads.", "NWS Hanford CA")])),
    "calm": ("CAZ159", lambda tz: dict(
        hours=_hours(tz, _heat_curve(72), lambda h: 50),
        aqi=_aqi(tz, 35, [38, 40]),
        alerts=[])),
    # Only an excluded short-fuse warning: must never trigger the agent
    "tornado_warning": ("MNZ060", lambda tz: dict(
        hours=_hours(tz, lambda h: 78, lambda h: 70, precip_at=lambda h: 50, short_at=lambda h: "Thunderstorms"),
        aqi=_aqi(tz, 30, [30, 30]),
        alerts=[_nws(tz, "Tornado Warning", "Extreme", 1, "Tornado Warning for Hennepin County",
                     "A tornado was observed.", "Take shelter now.", "NWS Twin Cities MN")])),
    "winter_storm": ("MNZ060", lambda tz: dict(
        hours=_hours(tz, lambda h: 12, lambda h: 85, precip_at=lambda h: 90, short_at=lambda h: "Heavy Snow",
                     wind_at=lambda h: 35),
        aqi=_aqi(tz, 20, [20, 20]),
        alerts=[_nws(tz, "Winter Storm Warning", "Severe", 30, "Winter Storm Warning through tomorrow night",
                     "Heavy snow, total accumulations of 10 to 14 inches, wind gusts to 40 mph.",
                     "If you must travel, keep an extra flashlight, food, and water in your vehicle.",
                     "NWS Twin Cities MN")])),
}


def build(name: str, zone_id: str | None = None) -> dict:
    default_zone, make = SCENARIOS[name]
    z = _zone(zone_id or default_zone)
    return assemble(z["zone"], make(ZoneInfo(z["tz"])), name)


# Public building blocks (used by the eval set to make edge cases)
hours, aqi, nws_alert, heat_curve = _hours, _aqi, _nws, _heat_curve


def assemble(zone_id: str, parts: dict, name: str) -> dict:
    """parts = {"hours": [...], "aqi": {...} | None, "alerts": [...]} -> snapshot."""
    z = _zone(zone_id)
    tz = ZoneInfo(z["tz"])
    handled = [a for a in parts["alerts"] if not hazards.is_excluded(a["event"])]
    excluded = [a for a in parts["alerts"] if hazards.is_excluded(a["event"])]
    summary = snapshot.summarize(parts["hours"], parts["aqi"], handled)
    now = datetime.now(tz).isoformat(timespec="seconds")
    return {"zone": z["zone"], "name": z["name"], "place": z.get("place"), "state": z.get("state"), "tz": z["tz"],
            "demo": True, "generated_at": now, "forecast_fetched_at": now, "aqi_fetched_at": now,
            "forecast": {"source": f"scenario:{name}", "hours": parts["hours"]}, "aqi": parts["aqi"],
            "alerts": handled, "excluded_alerts": [{"event": a["event"], "ends": a["ends"]} for a in excluded],
            "summary": summary, "errors": {}, "fingerprint": snapshot.fingerprint(summary, handled),
            "scenario": name}
