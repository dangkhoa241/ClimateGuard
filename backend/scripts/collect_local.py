"""Run the collector locally (STORAGE=local) and print a one-line summary per zone.

Usage: python scripts/collect_local.py [ZONE ...] [--monitor]   (default: all monitored zones)
  --monitor  also run the monitoring agent for zones whose data changed (live Baseten calls)
Snapshots are written to backend/.local/snapshots/<ZONE>.json
"""
import json
import sys

import _path  # noqa: F401

from climateguard import zones
from climateguard.handlers.collect import collect, monitor_changed
from climateguard.store import get_store

args = [a.upper() for a in sys.argv[1:] if not a.startswith("--")]
zone_list = [zones.get(z) for z in args] if args else None
if zone_list and None in zone_list:
    sys.exit(f"unknown zone(s): {[z for z, r in zip(args, zone_list) if r is None]}")
result = collect(zone_list)
store = get_store()
for slug in result["changed"] + result["unchanged"]:
    snap = store.get_latest(slug)
    s = snap["summary"]
    excluded = [a["event"] for a in snap["excluded_alerts"]]
    print(f"{slug} {(snap.get('place') or snap['name'])[:22]:22} max {s.get('max_temp_f')}F min {s.get('min_temp_f')}F "
          f">=95F: {s.get('hours_ge_95f')}h  AQI {s['aqi_now']} {s['aqi_category_now']} [{snap['aqi']['source']}]  "
          f"alerts: {s['active_alerts'] or '-'}{f'  NOT COVERED: {excluded}' if excluded else ''}  "
          f"fc: {snap['forecast']['source']}  fp={snap['fingerprint']}{'  CHANGED' if slug in result['changed'] else ''}")
problems = {k: v for k, v in result.items() if k in ("failed", "partial") and v}
if problems:
    print(json.dumps(problems, indent=1))
if "--monitor" in sys.argv:
    for slug, d in monitor_changed(result).items():
        print(f"agent {slug}: {d['action']} - {d['reason']}")
