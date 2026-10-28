"""Replay a REAL past event through the live monitoring agent (Baseten), moment by moment.

Usage:
  python scripts/replay.py                      # list events and moments
  python scripts/replay.py heat_2022            # all moments in order (one REPLAY-heat_2022 history)
  python scripts/replay.py flood_2023 watch     # one moment
Runs in the REPLAY-<event> namespace: nothing is emailed, nothing enters the live decision history.
"""
import sys

import _path  # noqa: F401

from climateguard import alerts_store, replays
from climateguard.monitor import run_monitor

sys.stdout.reconfigure(encoding="utf-8")
if len(sys.argv) < 2:
    for c in replays.catalog():
        print(f"{c['event']:11} {c['title']} ({c['place']}, zone {c['zone']})")
        for m in c["moments"]:
            print(f"   {m['id']:22} {m['at_local'][:16]}  {m['label']}")
    sys.exit()

event = sys.argv[1]
moments = sys.argv[2:] or replays.moments(event)
alerts_store.clear_local(f"REPLAY-{event}")
info = replays.load(event)
print(f"{replays.BANNER}\n{info['title']}: {info['facts']}\n{replays.STORY.get(event, '')}\n")
for m in moments:
    snap = replays.snapshot_for(event, m)
    d = run_monitor(snap["zone"], snap)
    print(f"== {snap['replay']['at_local'][:16]}  {snap['replay']['label']}: {d['action'].upper()} "
          f"({d.get('model_calls', 0)} model calls, ${d.get('cost_usd', 0):.4f})")
    for s in d.get("sent", []):
        print(f"   [{s['severity']} {s['hazard']}]")
        for lang, msg in s["messages"].items():
            print(f"     {lang}: {msg}")
    if not d.get("sent"):
        print(f"   why: {d['reason']}")
