"""Run the collector locally (STORAGE=local) and print a one-line summary per city.

Usage: python scripts/collect_local.py [city ...] [--monitor]   (default: all cities)
  --monitor  also run the monitoring agent for cities whose data changed (live Baseten calls)
Snapshots are written to backend/.local/snapshots/<city>.json
"""
import json
import sys

import _path  # noqa: F401

from climateguard.handlers.collect import collect, monitor_changed
from climateguard.store import get_store

args = [a for a in sys.argv[1:] if not a.startswith("--")]
result = collect(args or None)
store = get_store()
for slug in result["changed"] + result["unchanged"]:
    snap = store.get_latest(slug)
    s = snap["summary"]
    print(f"{snap['name']:9} max {s.get('max_temp_f')}F (HI {s.get('max_heat_index_f')}F)  "
          f">=95F: {s.get('hours_ge_95f')}h  AQI {s['aqi_now']} {s['aqi_category_now']} "
          f"[{snap['aqi']['source']}]  alerts: {s['active_alerts'] or '-'}  "
          f"forecast: {snap['forecast']['source']}  fp={snap['fingerprint']}"
          f"{'  CHANGED' if slug in result['changed'] else ''}")
print(json.dumps({k: v for k, v in result.items() if k in ("failed", "partial") and v}, indent=1) or "")
if "--monitor" in sys.argv:
    for slug, d in monitor_changed(result).items():
        print(f"agent {slug}: {d['action']} - {d['reason']}")
