"""Build real-event replays from public archives (run once; output is committed).

For each event and each chosen moment T, this saves what ClimateGuard would have seen at T:
  - hourly weather for the next 48 h: OBSERVED airport readings (IEM ASOS archive). Archived NWS
    hourly forecasts are not available, so replays use what actually happened, labeled as such.
  - NWS watches/warnings/advisories in effect (or already issued) at T, with the real NWS text
    and end time as of the latest product before T (IEM VTEC archive)
  - air quality at T (AirNow hourly file archive) and daily county AQI (EPA AirData)

Usage: python scripts/build_replays.py [event ...]   -> backend/src/climateguard/data/replays/<event>.json
"""
import csv
import io
import json
import re
import sys
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import _path  # noqa: F401
import requests

from climateguard import config, risk

IEM = "https://mesonet.agron.iastate.edu"
OUT = Path(__file__).resolve().parents[1] / "src" / "climateguard" / "data" / "replays"
CACHE = config.LOCAL_DIR / "replay-downloads"
S = requests.Session()
S.headers["User-Agent"] = config.NWS_USER_AGENT

EVENTS = {
    "heat_2022": {
        "title": "September 2022 California heat wave",
        "zone": "CAZ159", "place": "Stockton, CA", "historic_ugc": ["CAZ019", "CAC077"],
        "tz": "America/Los_Angeles", "station": "SCK", "aq_sites": ["Stockton"],
        "county": ("California", "San Joaquin"), "vtec_window": ("2022-08-29", "2022-09-12"),
        "facts": ("NWS Sacramento issued an Excessive Heat Warning for the Northern San Joaquin Valley in effect "
                  "Sept 4-9, 2022. Stockton tied its all-time record high of 115F on Sept 6, the day Sacramento "
                  "set its all-time record of 116F. (Hourly airport readings in this replay peak at 114F.)"),
        "moments": [
            ("warning_issued", "2022-09-01T10:00", "Warning already issued for the weekend"),
            ("warning_starts", "2022-09-04T09:00", "First day of the warning"),
            ("record_day_morning", "2022-09-06T07:00", "Morning of the record day (115F)"),
            ("record_day_afternoon", "2022-09-06T15:00", "Afternoon of the record day"),
            ("after", "2022-09-10T10:00", "The day after the warning ended"),
        ],
    },
    "flood_2023": {
        "title": "January 2023 Merced County floods (Planada)",
        "zone": "CAZ303", "place": "Planada, CA", "historic_ugc": ["CAC047", "CAZ300", "CAZ301"],
        "tz": "America/Los_Angeles", "station": "MCE", "aq_sites": ["Merced"],
        "county": ("California", "Merced"), "vtec_window": ("2023-01-06", "2023-01-21"),
        "facts": ("Atmospheric-river storms flooded Merced County. Bear Creek reached a record stage on the "
                  "morning of Jan 10, 2023, and the entire town of Planada (about 4,000 people, many of them "
                  "farmworker families) was ordered to evacuate."),
        "moments": [
            ("watch", "2023-01-08T10:00", "Flood Watch ahead of the storm"),
            ("warning_night", "2023-01-09T22:00", "Night of Jan 9: flood warnings issued"),
            ("evacuation_morning", "2023-01-10T06:00", "Morning of Jan 10: Planada evacuated"),
            ("after", "2023-01-20T12:00", "After the warnings ended"),
        ],
    },
    "smoke_2020": {
        "title": "September 2020 wildfire smoke",
        "zone": "CAZ159", "place": "Stockton, CA", "historic_ugc": ["CAZ019", "CAC077"],
        "tz": "America/Los_Angeles", "station": "SCK", "aq_sites": ["Stockton"],
        "county": ("California", "San Joaquin"), "vtec_window": ("2020-09-07", "2020-09-17"),
        "facts": ("Smoke from the August Complex, Creek and other wildfires filled the Central Valley. San Joaquin "
                  "County's daily AQI reached 206 (Very Unhealthy) on Sept 12, 2020."),
        "moments": [
            ("orange_sky", "2020-09-09T12:00", "Smoke turns the sky orange"),
            ("peak", "2020-09-12T14:00", "Peak: county AQI 206 (Very Unhealthy)"),
            ("improving", "2020-09-16T12:00", "Smoke improving"),
        ],
    },
}

SEVERITY_BY_SIG = {"W": "Severe", "A": "Moderate", "Y": "Minor", "S": "Minor"}
VTEC_RE = re.compile(r"/O\.(\w{3})\.K?(\w{3,4})\.(\w\w)\.(\w)\.(\d{4})\.(\d{6}T\d{4}Z)-(\d{6}T\d{4}Z)/")


def cached_get(url: str, name: str, binary=False):
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / name
    if not path.exists():
        r = S.get(url, timeout=60)
        r.raise_for_status()
        path.write_bytes(r.content)
    return path.read_bytes() if binary else path.read_text(encoding="utf-8", errors="replace")


def vt_time(s: str):
    return None if s.startswith("000000") else datetime.strptime(s, "%y%m%dT%H%MZ").replace(tzinfo=timezone.utc)


# --- weather: observed hourly from the airport station ------------------------

def observed_hours(ev: dict, at: datetime) -> list[dict]:
    tz = ZoneInfo(ev["tz"])
    start, end = at - timedelta(hours=1), at + timedelta(hours=49)
    url = (f"{IEM}/cgi-bin/request/asos.py?station={ev['station']}&data=tmpf&data=relh&data=sknt&data=p01i"
           f"&year1={start.year}&month1={start.month}&day1={start.day}&year2={end.year}&month2={end.month}"
           f"&day2={end.day}&tz={ev['tz'].replace('/', '%2F')}&format=onlycomma&latlon=no&missing=empty"
           f"&trace=0.0001&report_type=3")
    text = cached_get(url, f"asos_{ev['station']}_{start:%Y%m%d}_{end:%Y%m%d}.csv")
    by_hour: dict[datetime, dict] = {}
    for r in csv.DictReader(io.StringIO(text)):
        if not r.get("tmpf"):
            continue
        t = datetime.strptime(r["valid"], "%Y-%m-%d %H:%M").replace(tzinfo=tz)
        hour = (t + timedelta(minutes=30)).replace(minute=0)  # :53/:55 reports belong to the next hour
        by_hour.setdefault(hour, r)
    out, h = [], at.replace(minute=0)
    while len(out) < 48:
        r = by_hour.get(h)
        if r:
            temp, rh = float(r["tmpf"]), float(r["relh"]) if r.get("relh") else 30.0
            rain = float(r["p01i"]) if r.get("p01i") else 0.0
            out.append({"time": h.isoformat(), "temp_f": round(temp), "rh": round(rh),
                        "heat_index_f": round(risk.heat_index_f(temp, rh)),
                        "wind_mph": round(float(r["sknt"]) * 1.15078) if r.get("sknt") else None,
                        # observed, not forecast: rain that actually fell in this hour
                        "precip_prob": 90 if rain >= 0.01 else 5, "precip_in": round(rain, 2),
                        "short": "Rain" if rain >= 0.01 else None})
        h += timedelta(hours=1)
        if h > at + timedelta(hours=60):
            break
    return out


# --- air quality ---------------------------------------------------------------

def aqi_at(ev: dict, at: datetime) -> dict:
    utc = at.astimezone(timezone.utc)
    name = f"HourlyAQObs_{utc:%Y%m%d%H}.dat"
    text = cached_get(f"https://files.airnowtech.org/airnow/{utc:%Y}/{utc:%Y%m%d}/{name}", name)
    pm25, other = [], []
    for r in csv.DictReader(io.StringIO(text)):
        if any(r["SiteName"].startswith(p) for p in ev["aq_sites"]):
            for col, bucket in (("PM25_AQI", pm25), ("OZONE_AQI", other), ("PM10_AQI", other)):
                try:
                    bucket.append(int(float(r[col])))
                except (TypeError, ValueError):
                    pass
    if not pm25 and not other:
        return None
    worst_pm, worst_other = max(pm25, default=None), max(other, default=None)
    aqi = max(v for v in (worst_pm, worst_other) if v is not None)
    year_zip = cached_get(f"https://aqs.epa.gov/aqsweb/airdata/daily_aqi_by_county_{at.year}.zip",
                          f"daily_aqi_by_county_{at.year}.zip", binary=True)
    with zipfile.ZipFile(io.BytesIO(year_zip)) as z:
        daily = list(csv.DictReader(io.TextIOWrapper(z.open(z.namelist()[0]), encoding="utf-8")))
    days = {(at + timedelta(days=d)).strftime("%Y-%m-%d") for d in (0, 1)}
    forecast = [{"date": r["Date"], "aqi": int(r["AQI"]), "category": r["Category"],
                 "pollutant": r["Defining Parameter"], "action_day": int(r["AQI"]) > 100}
                for r in daily if (r["State Name"], r["county Name"]) == ev["county"] and r["Date"] in days]
    return {"source": "airnow-archive+epa-airdata",
            "current": {"aqi": aqi, "category": risk.aqi_category(aqi),
                        "pollutant": "PM2.5" if worst_pm is not None and worst_pm >= (worst_other or 0) else "O3",
                        "pm25_aqi": worst_pm, "observed_at": at.isoformat(), "area": ev["aq_sites"][0]},
            "forecast": sorted(forecast, key=lambda f: f["date"])}


# --- NWS products (IEM VTEC archive) --------------------------------------------

def vtec_events(ev: dict) -> list[dict]:
    seen, out = set(), []
    a, b = ev["vtec_window"]
    for ugc in ev["historic_ugc"]:
        d = json.loads(cached_get(f"{IEM}/json/vtec_events_byugc.py?ugc={ugc}&sdate={a}&edate={b}",
                                  f"vtec_{ugc}_{a}_{b}.json"))
        for e in d.get("events", []):
            key = (e["wfo"], e["phenomena"], e["significance"], e["eventid"])
            if key not in seen:
                seen.add(key)
                out.append(e)
    return out


def _segment(text: str, etn: int, phen: str, sig: str) -> str:
    for seg in text.split("$$"):
        if any(m.group(3) == phen and m.group(4) == sig and int(m.group(5)) == etn for m in VTEC_RE.finditer(seg)):
            return seg
    return ""


ISSUED_RE = re.compile(r"^\d{3,4} (AM|PM) [A-Z]{3,4} \w{3} \w{3} \d{1,2} \d{4}\s*$")


def _clean(seg: str) -> tuple[str, str]:
    """Plain-language message only: skip zone codes, the VTEC line and area names, which end at
    the segment's issue-time line ("150 AM PDT Wed Aug 31 2022")."""
    lines = seg.splitlines()
    issued = [i for i, l in enumerate(lines) if ISSUED_RE.match(l.strip())]
    after = issued[-1] + 1 if issued else 0
    start = next((i for i, l in enumerate(lines) if i >= after and (l.startswith("...") or l.startswith("* WHAT"))),
                 after)
    body = "\n".join(lines[start:])
    instr = ""
    m = re.search(r"PRECAUTIONARY/PREPAREDNESS ACTIONS\.\.\.\s*(.+?)(?:&&|\Z)", body, re.S)
    if m:
        instr, body = m.group(1), body[:m.start()]
    tidy = lambda s: re.sub(r"\s+", " ", s).strip()  # noqa: E731
    return tidy(body)[:1200], tidy(instr)[:1200]


def _all_products(ev: dict) -> list[tuple[datetime, str]]:
    """Every archived NWS product for the events in the window. One product can change several
    events (e.g. a warning product carries the UPG line that ends the watch it replaces)."""
    prods = {}
    for e in vtec_events(ev):
        q = _event_query(e)
        d = json.loads(cached_get(f"{IEM}/json/vtec_event.py?{q}", f"vtec_event_{q.replace('&', '_')}.json"))
        for p in [d["report"]] + list(d.get("svs") or []):
            prods[p["product_id"]] = (datetime.fromisoformat(p["valid"].replace("Z", "+00:00")), p["text"])
    return sorted(prods.values(), key=lambda x: x[0])


def _event_query(e: dict) -> str:
    return (f"wfo={e['wfo']}&year={e['url'].split('year=')[1][:4]}&phenomena={e['phenomena']}"
            f"&significance={e['significance']}&etn={e['eventid']}")


def alerts_at(ev: dict, at: datetime) -> list[dict]:
    out, at_utc = [], at.astimezone(timezone.utc)
    products = _all_products(ev)
    for e in vtec_events(ev):
        phen, sig, etn = e["phenomena"], e["significance"], int(e["eventid"])
        q = _event_query(e)
        state = None  # latest (valid, action, begin, end, segment) for this event at or before `at`
        for valid, text in products:
            if valid > at_utc:
                break
            seg = _segment(text, etn, phen, sig)
            for m in VTEC_RE.finditer(seg):
                if m.group(3) == phen and m.group(4) == sig and int(m.group(5)) == etn:
                    state = (valid, m.group(1), vt_time(m.group(6)), vt_time(m.group(7)), seg)
        if not state:
            continue  # not issued yet at this moment
        valid, action, begin, end, seg = state
        if action in ("CAN", "EXP", "UPG") or (end and end <= at_utc):
            continue  # cancelled, expired, or upgraded (e.g. watch -> warning) before this moment
        desc, instr = _clean(seg)
        tz = ZoneInfo(ev["tz"])
        out.append({"id": f"{e['wfo']}-{e['phenomena']}.{e['significance']}-{e['eventid']}", "event": e["name"],
                    "message_type": "Update" if action not in ("NEW",) else "Alert",
                    "severity": SEVERITY_BY_SIG.get(e["significance"], "Unknown"), "urgency": "Expected",
                    "certainty": "Likely", "headline": f"{e['name']} issued by NWS {e['wfo']}",
                    "description": desc, "instruction": instr, "sent": valid.astimezone(tz).isoformat(),
                    "onset": begin.astimezone(tz).isoformat() if begin else None,
                    "ends": end.astimezone(tz).isoformat() if end else None,
                    "expires": end.astimezone(tz).isoformat() if end else None, "references": [],
                    "sender": f"NWS {e['wfo']}", "ugc": [],
                    "archive_url": f"{IEM}/vtec/?{q}"})
    return out


def build(event_id: str) -> dict:
    ev = EVENTS[event_id]
    tz = ZoneInfo(ev["tz"])
    moments = []
    for mid, at_s, label in ev["moments"]:
        at = datetime.fromisoformat(at_s).replace(tzinfo=tz)
        m = {"id": mid, "at_local": at.isoformat(), "label": label, "hours": observed_hours(ev, at),
             "aqi": aqi_at(ev, at), "alerts": alerts_at(ev, at)}
        print(f"  {event_id}/{mid:22} {at:%Y-%m-%d %H:%M}  hours={len(m['hours'])} "
              f"max={max((h['temp_f'] for h in m['hours'][:24]), default=None)}F  "
              f"AQI={(m['aqi'] or {}).get('current', {}).get('aqi')}  alerts={[a['event'] for a in m['alerts']]}")
        moments.append(m)
    return {"event": event_id, "title": ev["title"], "zone": ev["zone"], "place": ev["place"], "tz": ev["tz"],
            "historic_ugc": ev["historic_ugc"], "facts": ev["facts"],
            "sources": {"weather": f"Observed hourly readings, airport station {ev['station']} (IEM ASOS archive)",
                        "alerts": "NWS products from the IEM VTEC archive (original text)",
                        "air_quality": "AirNow hourly archive (files.airnowtech.org) and EPA AirData daily county AQI"},
            "note": "Replays use observed weather in place of the forecast; archived NWS hourly forecasts are not available.",
            "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "moments": moments}


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    for eid in sys.argv[1:] or list(EVENTS):
        data = build(eid)
        (OUT / f"{eid}.json").write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"wrote {OUT / f'{eid}.json'}")
