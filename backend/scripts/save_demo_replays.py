"""Save the demo's fallback replay results from earlier REAL agent runs (no model calls).

Reads the local REPLAY-<event> and EVAL-real_* logs (written by replay.py and run_eval.py), keeps the
latest "sent" decision for each demo moment (demo.DEMO_MOMENTS), and writes
src/climateguard/data/replays/demo_saved.json (committed). The demo shows these when the daily budget
is spent, the rate limit is reached, or a live run is too slow.

Usage: python scripts/save_demo_replays.py
"""
import json
import sys

import _path  # noqa: F401

from climateguard import config, demo

sys.stdout.reconfigure(encoding="utf-8")
found = {}
for path in sorted((config.LOCAL_DIR / "alerts").glob("*.jsonl")):
    if not path.stem.startswith(("REPLAY-", "EVAL-real_")):
        continue
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    decisions = [r for r in rows if r.get("kind") == "decision"]
    if len({(r.get("replay") or {}).get("moment") for r in decisions}) > 1:
        continue  # multi-step cases: the agent saw earlier moments, a single demo run never does
    for r in decisions:
        rep = r.get("replay") or {}
        if r.get("action") != "sent":
            continue
        if demo.DEMO_MOMENTS.get(rep.get("event")) != rep.get("moment"):
            continue
        if rep["event"] not in found or r["ts"] > found[rep["event"]]["ran_at"]:
            found[rep["event"]] = {"ran_at": r["ts"], "action": r["action"], "reason": r["reason"],
                                   "model_calls": r.get("model_calls", 0), "cost_usd": r.get("cost_usd", 0),
                                   "sent": [{"hazard": s["hazard"], "severity": s["severity"],
                                             "messages": s["messages"]} for s in r.get("sent", [])]}

missing = sorted(set(demo.DEMO_MOMENTS) - set(found))
if missing:
    sys.exit(f"no saved run for {missing}: run `python scripts/replay.py <event> <moment>` first")
demo.SAVED_PATH.write_text(json.dumps(found, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
for e, d in found.items():
    print(f"{e:11} {d['ran_at'][:16]}  {d['action']}  ${d['cost_usd']:.4f}  {[s['hazard'] for s in d['sent']]}")
print(f"wrote {demo.SAVED_PATH}")
