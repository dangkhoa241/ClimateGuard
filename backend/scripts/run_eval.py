"""Run the evaluation set against the live monitoring agent (Baseten) and report:
decision accuracy, hazard and severity accuracy, guardrail catches, medical-safety of every
sent message, cost per alert and latency.

Usage:
  python scripts/run_eval.py                 # all cases (~$0.20-0.40)
  python scripts/run_eval.py real_flood_watch edge_calm
  python scripts/run_eval.py --fresh         # bypass the 1-hour response cache (new samples)
Results: backend/eval/results/<timestamp>.json and .md
Every case runs in its own EVAL-<id> namespace: nothing is emailed and nothing touches live data.
"""
import json
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path

import _path  # noqa: F401

from climateguard import alerts_store, config
from climateguard.monitor import MEDICAL_TERMS, SEVERITIES, run_monitor
from eval_cases import CASES

OUT = Path(__file__).resolve().parents[1] / "eval" / "results"


REJECTION_KINDS = [  # (phrase in monitor.validate_alert's message, category)
    ("duplicate", "duplicate"), ("daily cap", "cap"), ("symptoms/diagnosis/medicine", "medical_wording"),
    ("missing message", "missing_language"), ("characters", "too_long"), ("only for zone", "wrong_zone"),
    ("diacritics/accents", "missing_diacritics"),
]


def rejection_kind(reason: str) -> str:
    return next((kind for phrase, kind in REJECTION_KINDS if phrase in reason), "other")


def score_step(expect: dict, d: dict, prev: dict | None) -> dict:
    sent = {s["hazard"]: s["severity"] for s in d.get("sent", [])}
    checks = {}
    if "send" in expect:
        checks["decision"] = (d["action"] == "sent") == expect["send"]
    if expect.get("send") and expect.get("hazards"):
        checks["hazards"] = set(expect["hazards"]) <= set(sent)
        if expect.get("severity"):
            checks["severity"] = all(sent.get(h) in expect["severity"] for h in expect["hazards"] if h in sent)
    if expect.get("no_repeat"):
        checks["no_repeat"] = not (set(expect["no_repeat"]) & set(sent))
    if expect.get("escalate"):
        h = expect["escalate"]
        before = {s["hazard"]: s["severity"] for s in (prev or {}).get("sent", [])}.get(h)
        checks["escalate"] = h in sent and (before is None or SEVERITIES[sent[h]] > SEVERITIES[before])
    if expect.get("zero_calls"):
        checks["zero_calls"] = (d.get("model_calls") or 0) == 0
    msgs = [m for s in d.get("sent", []) for m in s["messages"].values()]
    checks["no_medical_wording"] = not any(MEDICAL_TERMS.search(m) for m in msgs)
    checks["proper_accents"] = all(not s["messages"].get("vi", "x").isascii() for s in d.get("sent", []))
    return checks


def run_case(case: dict) -> dict:
    ns = f"EVAL-{case['id']}"
    alerts_store.clear_local(ns)
    for hazard, severity in case.get("seed", []):
        alerts_store.record_sent(ns, hazard, severity, {"en": "seed", "es": "seed", "vi": "seed"}, "eval seed")
    steps, prev = [], None
    for make, expect in case["steps"]:
        snap = make()
        t0 = time.time()
        d = run_monitor(snap["zone"], snap, namespace=ns)
        latency = time.time() - t0
        checks = score_step(expect, d, prev)
        rejections = [rejection_kind(t["rejected"]) for t in d.get("tools", []) if t.get("rejected")]
        steps.append({"action": d["action"], "reason": d["reason"], "sent": [
            {"hazard": s["hazard"], "severity": s["severity"], "en": s["messages"]["en"]} for s in d.get("sent", [])],
            "checks": checks, "passed": all(checks.values()), "rejections": rejections,
            "model_calls": d.get("model_calls") or 0, "cost_usd": d.get("cost_usd") or 0.0,
            "latency_s": round(latency, 2), "signals": d.get("signals", [])})
        prev = d
    return {"id": case["id"], "kind": case["kind"], "desc": case["desc"], "steps": steps,
            "passed": all(s["passed"] for s in steps)}


def summarize(results: list[dict]) -> dict:
    steps = [s for r in results for s in r["steps"]]
    def rate(key):
        vals = [s["checks"][key] for s in steps if key in s["checks"]]
        return {"passed": sum(vals), "total": len(vals)}
    alerts = sum(len(s["sent"]) for s in steps)
    cost = sum(s["cost_usd"] for s in steps)
    lat = [s["latency_s"] for s in steps if s["model_calls"]]
    rej: dict[str, int] = {}
    for s in steps:
        for k in s["rejections"]:
            rej[k] = rej.get(k, 0) + 1
    return {"cases": {"passed": sum(r["passed"] for r in results), "total": len(results)},
            "by_kind": {k: {"passed": sum(r["passed"] for r in results if r["kind"] == k),
                            "total": sum(r["kind"] == k for r in results)} for k in ("real", "edge")},
            "decision_accuracy": rate("decision"), "hazard_accuracy": rate("hazards"),
            "severity_in_range": rate("severity"), "no_repeat": rate("no_repeat"), "escalation": rate("escalate"),
            "pre_filter_zero_calls": rate("zero_calls"), "no_medical_wording": rate("no_medical_wording"),
            "proper_accents": rate("proper_accents"),
            "guardrail_rejections": rej, "alerts_sent": alerts, "model_calls": sum(s["model_calls"] for s in steps),
            "total_cost_usd": round(cost, 4), "cost_per_alert_usd": round(cost / alerts, 4) if alerts else None,
            "latency_s": {"p50": round(statistics.median(lat), 2) if lat else None,
                          "p95": round(sorted(lat)[max(0, int(len(lat) * 0.95) - 1)], 2) if lat else None},
            "model": config.MONITOR_MODEL, "reasoning_effort": config.REASONING_EFFORT["baseten"]}


def markdown(summary: dict, results: list[dict]) -> str:
    f = lambda r: f"{r['passed']}/{r['total']}" if r["total"] else "n/a"  # noqa: E731
    lines = [f"# Monitoring agent eval: {datetime.now():%Y-%m-%d %H:%M}", "",
             f"Model `{summary['model']}`, reasoning effort `{summary['reasoning_effort']}`.", "",
             "| Metric | Result |", "|---|---|",
             f"| Cases passed | **{f(summary['cases'])}** (real {f(summary['by_kind']['real'])}, edge {f(summary['by_kind']['edge'])}) |",
             f"| Decision accuracy (send vs. skip) | {f(summary['decision_accuracy'])} |",
             f"| Right hazard | {f(summary['hazard_accuracy'])} |",
             f"| Severity in expected range | {f(summary['severity_in_range'])} |",
             f"| No repeated alert (dedup) | {f(summary['no_repeat'])} |",
             f"| Escalation sent | {f(summary['escalation'])} |",
             f"| Pre-filter: zero model calls | {f(summary['pre_filter_zero_calls'])} |",
             f"| Sent messages free of medical wording | {f(summary['no_medical_wording'])} |",
             f"| Vietnamese written with diacritics | {f(summary['proper_accents'])} |",
             f"| Guardrail rejections (agent corrected itself) | {summary['guardrail_rejections'] or 'none'} |",
             f"| Alerts sent / model calls | {summary['alerts_sent']} / {summary['model_calls']} |",
             f"| Total cost / cost per alert | ${summary['total_cost_usd']} / ${summary['cost_per_alert_usd']} |",
             f"| Latency per run (p50 / p95) | {summary['latency_s']['p50']} s / {summary['latency_s']['p95']} s |",
             "", "| Case | Result | What the agent did |", "|---|---|---|"]
    for r in results:
        did = "; ".join(f"{s['action']}" + (f" ({', '.join(a['severity'] + ' ' + a['hazard'] for a in s['sent'])})"
                                             if s["sent"] else "")
                        + ("" if s["passed"] else f" FAILED {[k for k, v in s['checks'].items() if not v]}")
                        for s in r["steps"])
        lines.append(f"| `{r['id']}`: {r['desc']} | {'pass' if r['passed'] else '**FAIL**'} | {did} |")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if "--fresh" in sys.argv:
        config.CACHE_TTL_SECONDS = 0  # every call is a new sample
    cases = [c for c in CASES if not args or c["id"] in args]
    results = []
    for c in cases:
        r = run_case(c)
        results.append(r)
        print(f"{'PASS' if r['passed'] else 'FAIL'}  {c['id']:28} " + " | ".join(
            f"{s['action']}{'(' + ','.join(a['severity'][0] + ':' + a['hazard'] for a in s['sent']) + ')' if s['sent'] else ''}"
            f" {s['model_calls']}c ${s['cost_usd']:.4f} {s['latency_s']}s" for s in r["steps"]))
    summary = summarize(results)
    OUT.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    (OUT / f"{stamp}.json").write_text(json.dumps({"summary": summary, "results": results}, indent=1,
                                                  ensure_ascii=False), encoding="utf-8")
    md = markdown(summary, results)
    (OUT / f"{stamp}.md").write_text(md, encoding="utf-8")
    print("\n" + md.split("\n\n| Case")[0])
    print(f"\nSaved {OUT / (stamp + '.md')}")
