"""Lambda (EventBridge, every 15 min): refresh every monitored zone's snapshot, then run
the monitoring agent only for zones whose risk picture changed.

Monitored zones = zones with at least one confirmed subscriber, plus the demo zones.
Cost and scale controls:
  - NWS alerts: one national request per run, matched to zones by UGC code
  - forecasts / AirNow: reused for 45 min (they update hourly)
  - zones collected in parallel (COLLECT_WORKERS), agent runs in parallel (AGENT_WORKERS)
  - no model call when nothing changed; over the daily budget, only zones with a Warning
"""
import logging
from concurrent.futures import ThreadPoolExecutor

from .. import config, stats, subscriptions, zones
from ..snapshot import build_snapshot
from ..sources import nws
from ..store import get_store

log = logging.getLogger()
log.setLevel(logging.INFO)

# A source outage shouldn't look like "risk changed" (and trigger the agent).
CRITICAL_ERRORS = ("forecast", "aqi", "alerts")


def _collect_zone(zone: dict, national, store) -> tuple[str, str, object]:
    slug = zone["zone"]
    try:
        prev = store.get_latest(slug)
        snap = build_snapshot(zone, national, prev)
    except Exception as e:
        log.exception("snapshot failed for %s", slug)
        return slug, "failed", str(e)

    critical = [k for k in CRITICAL_ERRORS if k in snap["errors"]]
    if critical and prev:
        # Keep the last good snapshot rather than overwrite it with a blind one.
        return slug, "failed", f"kept previous snapshot; missing {critical}"

    changed = prev is None or prev.get("fingerprint") != snap["fingerprint"]
    store.put_snapshot(snap, changed=changed)
    log.info("%s fingerprint=%s changed=%s flags=%s excluded=%s", slug, snap["fingerprint"], changed,
             snap["summary"]["flags"], [a["event"] for a in snap["excluded_alerts"]])
    return slug, "changed" if changed else "unchanged", snap["errors"] or None


def collect(zone_list: list[dict] | None = None) -> dict:
    store = get_store()
    zone_list = zone_list if zone_list is not None else zones.monitored()
    try:
        national = nws.get_national_alerts()
    except Exception as e:
        log.warning("national alerts unavailable: %s", e)
        national = None

    result = {"zones": len(zone_list), "changed": [], "unchanged": [], "failed": {}, "partial": {}}
    with ThreadPoolExecutor(max_workers=max(1, config.COLLECT_WORKERS)) as pool:
        for slug, status, extra in pool.map(lambda z: _collect_zone(z, national, store), zone_list):
            if status == "failed":
                result["failed"][slug] = extra
                continue
            result[status].append(slug)
            if extra:
                result["partial"][slug] = extra
    return result


def monitor_changed(result: dict) -> dict:
    """Run the monitoring agent only for zones whose risk fingerprint changed."""
    if not result["changed"]:
        return {}  # nothing changed: skip even importing the agent
    from .. import budget
    from ..monitor import run_monitor

    over = budget.over_budget()
    store = get_store()

    def one(slug):
        try:
            skip = None
            if over and not budget.has_active_warning(store.get_latest(slug) or {}):
                skip = f"daily model budget (${config.DAILY_MODEL_BUDGET_USD:.2f}) used up; only zones with an NWS Warning run"
            d = run_monitor(slug, skip_reason=skip)
            return slug, {"action": d["action"], "reason": d["reason"], "cost_usd": d.get("cost_usd"),
                          "alerts_sent": len(d.get("sent") or [])}
        except Exception as e:  # one zone's agent failure must not block the others
            log.exception("monitor failed for %s", slug)
            return slug, {"action": "error", "reason": str(e)}

    with ThreadPoolExecutor(max_workers=max(1, config.AGENT_WORKERS)) as pool:
        return dict(pool.map(one, result["changed"]))


def handler(event, context):
    try:
        newly = subscriptions.refresh_confirmed()
        if newly:
            log.info("confirmed-subscriber counts changed for %s", newly)
    except Exception:
        log.exception("refreshing confirmed subscribers failed; using last known counts")
    result = collect()
    result["decisions"] = monitor_changed(result)
    try:
        stats.record(stats.summarize_run(result))
    except Exception:
        log.exception("recording daily stats failed")  # never fail a collection over counters
    log.info("collect result: %s", result)
    return result
