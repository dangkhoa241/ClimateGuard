"""Replays of REAL past events for demo mode and evaluation (built by scripts/build_replays.py).

Each replay is a list of moments; each moment becomes a normal snapshot (same shape as
snapshot.build_snapshot) plus a "replay" block that the app and the agent must surface:
it is a replay of a real event, not live data, and the weather is what was observed.
Runs on replay snapshots never email anyone and never enter the live decision history
(see monitor.run_monitor: separate REPLAY-<event> log).
"""
import json
from functools import lru_cache
from pathlib import Path

from . import hazards, snapshot, zones

DIR = Path(__file__).parent / "data" / "replays"

# Demo storyline. Maria is an EXAMPLE person; the events, places and data are real.
STORY = {
    "heat_2022": ("Example: Maria (an example person, not a real individual) works in the fields near Stockton "
                  "during the real September 2022 heat wave."),
    "flood_2023": ("Example: Maria's family (example people) lives in Planada during the real January 2023 "
                   "Merced County floods."),
    "smoke_2020": "Example: Maria (an example person) and her crew during the real September 2020 smoke.",
}
BANNER = "REPLAY of a real event, not live. Weather shown is what was observed."


@lru_cache(maxsize=None)
def load(event: str) -> dict:
    path = DIR / f"{event}.json"
    if not path.exists():
        raise KeyError(f"unknown replay {event!r}; available: {', '.join(available())}")
    return json.loads(path.read_text(encoding="utf-8"))


def available() -> list[str]:
    return sorted(p.stem for p in DIR.glob("*.json"))


def catalog() -> list[dict]:
    return [{"event": e, "title": (d := load(e))["title"], "place": d["place"], "zone": d["zone"],
             "facts": d["facts"], "story": STORY.get(e), "banner": BANNER,
             "moments": [{"id": m["id"], "label": m["label"], "at_local": m["at_local"]} for m in d["moments"]]}
            for e in available()]


def snapshot_for(event: str, moment: str) -> dict:
    d = load(event)
    m = next((x for x in d["moments"] if x["id"] == moment), None)
    if m is None:
        raise KeyError(f"unknown moment {moment!r} in {event}: {[x['id'] for x in d['moments']]}")
    z = zones.DEMO_ZONES[d["zone"]]
    alerts = [dict(a, hazard=hazards.group_for(a["event"])) for a in m["alerts"]]
    handled = [a for a in alerts if not hazards.is_excluded(a["event"])]
    excluded = [{"event": a["event"], "ends": a.get("ends")} for a in alerts if hazards.is_excluded(a["event"])]
    summary = snapshot.summarize(m["hours"], m["aqi"], handled)
    return {"zone": d["zone"], "name": z["name"], "place": d["place"], "state": z["state"], "tz": d["tz"],
            "demo": True, "generated_at": m["at_local"], "forecast_fetched_at": m["at_local"],
            "aqi_fetched_at": m["at_local"], "forecast": {"source": "replay:observed", "hours": m["hours"]},
            "aqi": m["aqi"], "alerts": handled, "excluded_alerts": excluded, "summary": summary, "errors": {},
            "fingerprint": snapshot.fingerprint(summary, handled),
            "replay": {"event": event, "title": d["title"], "moment": m["id"], "label": m["label"],
                       "at_local": m["at_local"], "facts": d["facts"], "story": STORY.get(event),
                       "banner": BANNER, "note": d["note"], "sources": d["sources"]}}


def moments(event: str) -> list[str]:
    return [m["id"] for m in load(event)["moments"]]
