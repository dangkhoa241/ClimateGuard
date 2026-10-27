"""Synthetic snapshots for testing the monitoring agent (and later, demo mode).

Shapes match snapshot.build_snapshot(); times start at the current hour so the
agent sees a plausible "now".
"""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from . import risk, snapshot
from .cities import TIMEZONE, get_city

_TZ = ZoneInfo(TIMEZONE)


def _hours(temp_at, rh_at, precip_at=lambda h: 0, short_at=lambda h: "Sunny", n=48):
    start = datetime.now(_TZ).replace(minute=0, second=0, microsecond=0)
    out = []
    for i in range(n):
        t = start + timedelta(hours=i)
        temp, rh = temp_at(t.hour), rh_at(t.hour)
        out.append({"time": t.isoformat(), "temp_f": temp, "rh": rh,
                    "heat_index_f": round(risk.heat_index_f(temp, rh)), "wind_mph": 8,
                    "precip_prob": precip_at(t.hour), "short": short_at(t.hour)})
    return out


def _aqi(now, fc, pollutant="PM2.5"):
    today = datetime.now(_TZ).date()
    return {"source": "scenario",
            "current": {"aqi": now, "category": risk.aqi_category(now), "pollutant": pollutant,
                        "pm25_aqi": now if pollutant == "PM2.5" else None,
                        "observed_at": datetime.now(_TZ).isoformat(timespec="seconds"), "area": None},
            "forecast": [{"date": str(today + timedelta(days=d)), "aqi": v, "category": risk.aqi_category(v),
                          "pollutant": pollutant, "action_day": v > 100} for d, v in enumerate(fc)]}


def _nws(event, severity, hours_from_now, headline, description, instruction):
    now = datetime.now(_TZ)
    ends = (now + timedelta(hours=hours_from_now)).isoformat(timespec="seconds")
    return {"id": f"scenario-{event.lower().replace(' ', '-')}", "event": event, "message_type": "Alert",
            "severity": severity, "urgency": "Expected", "certainty": "Likely", "headline": headline,
            "description": description, "instruction": instruction,
            "sent": now.isoformat(timespec="seconds"), "onset": now.isoformat(timespec="seconds"),
            "ends": ends, "expires": ends, "references": [], "sender": "NWS Sacramento CA"}


def _heat_curve(peak):
    # cool nights, peak at 4 PM
    return lambda h: round(peak - 30 + 30 * max(0.0, 1 - abs(h - 16) / 9))


SCENARIOS = {
    "heatwave": lambda: dict(
        hours=_hours(_heat_curve(108), lambda h: 22 if 10 <= h <= 20 else 45),
        aqi=_aqi(72, [78, 80]),
        alerts=[_nws("Extreme Heat Warning", "Severe", 36,
                     "Extreme Heat Warning in effect through tomorrow evening",
                     "Dangerously hot conditions with temperatures up to 108 expected.",
                     "Drink plenty of fluids, stay in an air-conditioned room, stay out of the sun.")]),
    "smoke": lambda: dict(
        hours=_hours(_heat_curve(88), lambda h: 30, short_at=lambda h: "Areas of Smoke"),
        aqi=_aqi(178, [185, 160]),
        alerts=[_nws("Air Quality Alert", "Unknown", 30, "Air Quality Alert due to wildfire smoke",
                     "Smoke from a wildfire will cause unhealthy air quality.",
                     "Limit time outdoors. Keep windows and doors closed.")]),
    "flood": lambda: dict(
        hours=_hours(lambda h: 52, lambda h: 95, precip_at=lambda h: 90, short_at=lambda h: "Heavy Rain"),
        aqi=_aqi(25, [20, 22]),
        alerts=[_nws("Flood Warning", "Severe", 24, "Flood Warning for low-lying areas near the Calaveras River",
                     "Heavy rain is causing flooding of low-lying areas and roads.",
                     "Turn around, don't drown when encountering flooded roads.")]),
    "calm": lambda: dict(
        hours=_hours(_heat_curve(72), lambda h: 50),
        aqi=_aqi(35, [38, 40]),
        alerts=[]),
}


def build(name: str, city: str = "stockton") -> dict:
    c = get_city(city)
    parts = SCENARIOS[name]()
    summary = snapshot.summarize(parts["hours"], parts["aqi"], parts["alerts"])
    return {"city": city, "name": c["name"], "generated_at": datetime.now(_TZ).isoformat(timespec="seconds"),
            "forecast": {"source": f"scenario:{name}", "hours": parts["hours"]}, "aqi": parts["aqi"],
            "alerts": parts["alerts"], "summary": summary, "errors": {},
            "fingerprint": snapshot.fingerprint(summary, parts["alerts"]), "scenario": name}
