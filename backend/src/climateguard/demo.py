"""Demo mode: replay one key moment of each real past event through the live monitoring agent.

A demo run uses its own fresh namespace (DEMO-<event>-<id>), so earlier runs never make the agent skip
as a duplicate, nothing is emailed (monitor.Run.live is False) and nothing enters the live decision
history. Identical runs within the cache TTL reuse the cached model answers and cost $0.

When a live run isn't possible (daily budget spent, rate limit reached, run too slow or failed), the
demo shows the result of an earlier REAL run of the same moment (data/demo_saved.json, built by
scripts/save_demo_replays.py), labeled with the date it ran.
"""
import json
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path

from . import replays, usage
from .languages import LANGS, REVIEWED
from .monitor import run_monitor
from .translate import translate_alert

# One button per event: the moment that shows the agent's judgment best.
DEMO_MOMENTS = {"heat_2022": "record_day_morning", "flood_2023": "warning_night", "smoke_2020": "peak"}
SAVED_PATH = Path(__file__).parent / "data" / "demo_saved.json"  # not in data/replays: that folder is the catalog
TRANSLATIONS_PATH = Path(__file__).parent / "data" / "demo_translations.json"
LIVE_WAIT_S = 23  # the Ask Lambda stops at 28 s and API Gateway at 30 s
LAUNCH_DAY = date(2026, 10, 27)  # first day of the deployed usage log
COST_CACHE_S = 900
FEATURES = {"monitor": "alerts", "translate": "alerts", "ask": "ask", "places": "ask", "places-search": "ask",
            "transcribe": "ask", "pretalk": "supervisor"}  # purpose prefix -> feature; recovery-* -> recovery

_pool = ThreadPoolExecutor(max_workers=2)
_cost = {"at": 0.0, "value": None}


@lru_cache(maxsize=None)
def saved() -> dict:
    return json.loads(SAVED_PATH.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def translations() -> dict:
    return json.loads(TRANSLATIONS_PATH.read_text(encoding="utf-8"))


def catalog() -> list[dict]:
    out = []
    for event, moment in DEMO_MOMENTS.items():
        d = replays.load(event)
        m = next(x for x in d["moments"] if x["id"] == moment)
        out.append({"event": event, "title": d["title"], "place": d["place"], "facts": d["facts"],
                    "story": replays.STORY.get(event), "banner": replays.BANNER, "moment": moment,
                    "moment_label": m["label"], "at_local": m["at_local"]})
    return out


def _alerts_in(sent: list[dict], event: str, lang: str, translate: bool) -> list[dict]:
    """Each sent alert in `lang`: the agent's own text for EN/ES/VI, otherwise an automatic translation of
    the English (labeled), or the English itself when translating isn't possible."""
    out = []
    for s in sent:
        msgs = s["messages"]
        fixture = translations().get(event, {}).get(s["hazard"])
        if fixture and fixture.get("en") == msgs.get("en"):
            text = fixture.get(lang, msgs["en"])
            shown = lang if lang in fixture else "en"
            auto = shown not in REVIEWED
        elif lang in msgs:
            text, shown, auto = msgs[lang], lang, False
        elif translate:
            text, auto = translate_alert(msgs["en"], lang)
            shown = lang if auto else "en"
        else:
            text, shown, auto = msgs["en"], "en", False
        alert = {"hazard": s["hazard"], "severity": s["severity"], "text": text, "lang": shown,
                 "automatic": auto}
        if fixture and fixture.get("en") == msgs.get("en"):
            alert["translations"] = fixture
        out.append(alert)
    return out


def _result(event: str, lang: str, decision: dict, *, source: str, why: str | None, translate: bool) -> dict:
    info = next(c for c in catalog() if c["event"] == event)
    calls, cost = int(decision.get("model_calls") or 0), round(float(decision.get("cost_usd") or 0), 4)
    return {**info, "source": source, "why": why, "ran_at": decision.get("ran_at") or decision.get("ts"),
            "emailed": False,
            "decision": {"action": decision["action"], "reason": decision["reason"], "model_calls": calls,
                         "cost_usd": cost, "cached": source == "live" and calls > 0 and cost == 0},
            "typical_cost_usd": round(float(saved()[event]["cost_usd"]), 4),
            "alerts": _alerts_in(decision.get("sent") or [], event, lang, translate)}


def saved_result(event: str, lang: str, why: str) -> dict:
    """An earlier real run of this moment. No model calls (not even translation)."""
    return _result(event, lang, saved()[event], source="saved", why=why, translate=False)


def _live(event: str, lang: str) -> dict:
    snap = replays.snapshot_for(event, DEMO_MOMENTS[event])
    decision = run_monitor(snap["zone"], snap, namespace=f"DEMO-{event}-{uuid.uuid4().hex[:8]}")
    if decision["action"] == "error":
        return saved_result(event, lang, "error")
    return _result(event, lang, decision, source="live", why=None, translate=lang not in REVIEWED)


def run(event: str, lang: str, wait_s: float = LIVE_WAIT_S) -> dict:
    """Live replay through the agent; the saved run if it fails or takes longer than `wait_s`."""
    if event not in DEMO_MOMENTS or lang not in LANGS:
        raise KeyError(event if event not in DEMO_MOMENTS else lang)
    future = _pool.submit(_live, event, lang)
    try:
        return future.result(timeout=wait_s)
    except FutureTimeout:
        return saved_result(event, lang, "slow")
    except Exception:
        return saved_result(event, lang, "error")


def cost_so_far() -> dict:
    """Real model spend of the deployed app since launch, from the usage log (cached for 15 minutes)."""
    if _cost["value"] is not None and time.time() - _cost["at"] < COST_CACHE_S:
        return _cost["value"]
    today = datetime.now(timezone.utc).date()
    days = [(LAUNCH_DAY + timedelta(days=i)).isoformat() for i in range((today - LAUNCH_DAY).days + 1)]
    by_feature = {"alerts": 0.0, "ask": 0.0, "supervisor": 0.0, "recovery": 0.0, "other": 0.0}
    for r in usage.records_for_days(days):
        prefix = str(r.get("purpose") or "").split(":")[0]
        feature = "recovery" if prefix.startswith("recovery") else FEATURES.get(prefix, "other")
        by_feature[feature] += float(r.get("cost_usd") or 0)
    value = {"since": LAUNCH_DAY.isoformat(), "total_usd": round(sum(by_feature.values()), 2),
             "by_feature": {k: round(v, 3) for k, v in by_feature.items()}}
    _cost.update(at=time.time(), value=value)
    return value
