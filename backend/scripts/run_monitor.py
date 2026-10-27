"""Run the monitoring agent for one city (live Baseten calls).

Usage:
  python scripts/run_monitor.py stockton                      # latest stored snapshot
  python scripts/run_monitor.py stockton --scenario heatwave  # synthetic: heatwave|smoke|flood|calm
  python scripts/run_monitor.py stockton --scenario heatwave --reset   # forget local sent alerts first
  add --force to skip the no-risk pre-filter, --effort low|medium|high to override reasoning effort
"""
import argparse
import json
import logging

import _path  # noqa: F401

from climateguard import alerts_store, scenarios
from climateguard.monitor import run_monitor

logging.basicConfig(level=logging.INFO, format="%(message)s")
for noisy in ("httpx", "openai", "urllib3"):
    logging.getLogger(noisy).setLevel(logging.WARNING)

p = argparse.ArgumentParser()
p.add_argument("city")
p.add_argument("--scenario", choices=sorted(scenarios.SCENARIOS))
p.add_argument("--reset", action="store_true")
p.add_argument("--force", action="store_true")
p.add_argument("--effort")
a = p.parse_args()

if a.reset:
    alerts_store.clear_local(a.city)
snap = scenarios.build(a.scenario, a.city) if a.scenario else None
d = run_monitor(a.city, snap, force=a.force, reasoning_effort=a.effort)

print(f"\n== {d['action'].upper()}  ({d.get('model_calls')} model calls, ${d.get('cost_usd', 0):.4f})")
print(f"why: {d['reason']}")
if d.get("signals"):
    print(f"signals: {d['signals']}")
for t in d.get("tools", []):
    print(f"  tool {t['tool']}({json.dumps(t['args'], ensure_ascii=False)})"
          + ("" if t["ok"] else f"  -> REJECTED: {t.get('rejected', 'error')}"))
for s in d.get("sent", []):
    print(f"\n  [{s['severity']} {s['hazard']}]")
    for lang, msg in s["messages"].items():
        print(f"   {lang}: {msg}")
