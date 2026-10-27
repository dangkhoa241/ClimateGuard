"""Lambda (EventBridge, every 15 min): refresh every city's snapshot, then run
the monitoring agent only for cities whose risk picture changed (cost control:
no model call when nothing changed).
"""
import logging

from ..cities import CITIES
from ..snapshot import build_snapshot
from ..store import get_store

log = logging.getLogger()
log.setLevel(logging.INFO)

# A source outage shouldn't look like "risk changed" (and trigger the agent).
CRITICAL_ERRORS = ("forecast", "aqi", "alerts")


def collect(cities=None) -> dict:
    store = get_store()
    result = {"changed": [], "unchanged": [], "failed": {}, "partial": {}}
    for slug in cities or CITIES:
        try:
            snap = build_snapshot(slug)
        except Exception as e:
            log.exception("snapshot failed for %s", slug)
            result["failed"][slug] = str(e)
            continue

        prev = store.get_latest(slug)
        critical = [k for k in CRITICAL_ERRORS if k in snap["errors"]]
        if critical and prev:
            # Keep the last good snapshot rather than overwrite it with a blind one.
            result["failed"][slug] = f"kept previous snapshot; missing {critical}"
            continue

        store.put_snapshot(snap)
        if snap["errors"]:
            result["partial"][slug] = snap["errors"]
        changed = prev is None or prev.get("fingerprint") != snap["fingerprint"]
        result["changed" if changed else "unchanged"].append(slug)
        log.info("%s fingerprint=%s changed=%s flags=%s", slug, snap["fingerprint"], changed,
                 snap["summary"]["flags"])
    return result


def monitor_changed(result: dict) -> dict:
    """Run the monitoring agent only for cities whose risk fingerprint changed."""
    if not result["changed"]:
        return {}  # nothing changed: skip even importing the agent
    from ..monitor import run_monitor

    decisions = {}
    for slug in result["changed"]:
        try:
            d = run_monitor(slug)
            decisions[slug] = {"action": d["action"], "reason": d["reason"], "cost_usd": d.get("cost_usd")}
        except Exception as e:  # one city's agent failure must not block the others
            log.exception("monitor failed for %s", slug)
            decisions[slug] = {"action": "error", "reason": str(e)}
    return decisions


def handler(event, context):
    result = collect()
    result["decisions"] = monitor_changed(result)
    log.info("collect result: %s", result)
    return result
