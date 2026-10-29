"""Offline tests for demo mode: replay buttons, isolation (never emailed, never live history), saved runs
when over budget / rate limited / slow, and the cost-so-far line."""
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]

import pytest

from climateguard import alerts_store, budget, config, demo, monitor, notify, replays, usage
from climateguard.handlers import api, ask as ask_handler


@pytest.fixture(autouse=True)
def local(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "LOCAL_DIR", tmp_path)
    monkeypatch.setattr(config, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(config, "USAGE_LOG", tmp_path / "usage.jsonl")
    monkeypatch.setattr(config, "STORAGE", "local")
    monkeypatch.setattr(config, "NOTIFY_MODE", "dryrun")
    monkeypatch.setattr(demo, "_cost", {"at": 0.0, "value": None})
    from climateguard import ratelimit
    ratelimit._local.clear()


def _event(body, ip="1.2.3.4"):
    return {"routeKey": "POST /demo/replay", "body": json.dumps(body), "requestContext": {"http": {"sourceIp": ip}}}


def _agent_sends(monkeypatch, seen=None):
    """A fake agent run that sends one heat alert through the real send path (validation skipped)."""
    def fake(zone, snapshot, *, namespace=None, **kw):
        if seen is not None:
            seen.append(namespace)
        run = monitor.Run(zone=zone, snapshot=snapshot, namespace=namespace)
        assert not run.live
        msgs = {"en": "Heat today.", "es": "Calor hoy.", "vi": "Hôm nay nóng."}
        alerts_store.record_sent(run.key, "heat", "extreme", msgs, "test")
        return alerts_store.log_decision(run.key, "sent", "Excessive Heat Warning active", model_calls=5,
                                         cost_usd=0.0151, sent=[{"hazard": "heat", "severity": "extreme",
                                                                 "messages": msgs}],
                                         replay={"event": "heat_2022", "moment": "record_day_morning"})
    monkeypatch.setattr(demo, "run_monitor", fake)


def test_one_button_per_real_event_each_labeled_replay():
    cat = demo.catalog()
    assert [c["event"] for c in cat] == ["heat_2022", "flood_2023", "smoke_2020"]
    for c in cat:
        assert c["banner"].startswith("REPLAY of a real event") and "example" in c["story"].lower()
        assert c["moment"] in replays.moments(c["event"])


def test_saved_runs_exist_for_every_button_in_reviewed_languages():
    for event in demo.DEMO_MOMENTS:
        s = demo.saved()[event]
        assert s["action"] == "sent" and s["cost_usd"] > 0 and s["model_calls"] > 0
        for alert in s["sent"]:
            assert set(alert["messages"]) >= {"en", "es", "vi"}


def test_saved_file_is_not_mistaken_for_a_replay_event():
    assert replays.available() == ["flood_2023", "heat_2022", "smoke_2020"]


def test_live_replay_is_isolated_and_never_emailed(monkeypatch):
    seen, delivered = [], []
    _agent_sends(monkeypatch, seen)
    monkeypatch.setattr(notify, "deliver", lambda *a, **k: delivered.append(a))
    r1 = demo.run("heat_2022", "es")
    r2 = demo.run("heat_2022", "es")
    assert r1["source"] == "live" and r1["why"] is None and r1["emailed"] is False and not delivered
    assert r1["alerts"] == [{"hazard": "heat", "severity": "extreme", "text": "Calor hoy.", "lang": "es",
                             "automatic": False}]
    assert r1["decision"]["cost_usd"] == 0.0151 and r1["decision"]["cached"] is False
    # a fresh namespace every run: an earlier demo run can never make the agent skip it as a duplicate
    assert len(set(seen)) == 2 and all(n.startswith("DEMO-heat_2022-") for n in seen)
    assert not alerts_store.recent_decisions("CAZ159")  # nothing under the live zone


def test_live_replay_translates_automatic_languages(monkeypatch):
    _agent_sends(monkeypatch)
    monkeypatch.setattr(demo, "translate_alert", lambda text, lang: (f"[{lang}] {text}", True))
    [a] = demo.run("heat_2022", "ko")["alerts"]
    assert a == {"hazard": "heat", "severity": "extreme", "text": "[ko] Heat today.", "lang": "ko", "automatic": True}


def test_cached_run_is_labeled(monkeypatch):
    def cached(zone, snapshot, *, namespace=None, **kw):
        return alerts_store.log_decision(namespace, "skipped", "no new risk", model_calls=3, cost_usd=0.0)
    monkeypatch.setattr(demo, "run_monitor", cached)
    r = demo.run("smoke_2020", "en")
    assert r["decision"] == {"action": "skipped", "reason": "no new risk", "model_calls": 3, "cost_usd": 0.0,
                             "cached": True}
    assert r["typical_cost_usd"] > 0 and r["alerts"] == []


@pytest.mark.parametrize("failure", ["error_decision", "exception", "slow"])
def test_failed_or_slow_live_run_shows_the_saved_run(monkeypatch, failure):
    def agent(zone, snapshot, *, namespace=None, **kw):
        if failure == "exception":
            raise RuntimeError("baseten down")
        if failure == "slow":
            time.sleep(0.5)
        return alerts_store.log_decision(namespace, "error", "boom")
    monkeypatch.setattr(demo, "run_monitor", agent)
    r = demo.run("flood_2023", "vi", wait_s=0.1)
    assert r["source"] == "saved" and r["why"] == ("slow" if failure == "slow" else "error")
    assert r["alerts"][0]["lang"] == "vi" and r["alerts"][0]["text"] == demo.saved()["flood_2023"]["sent"][0]["messages"]["vi"]
    assert r["ran_at"] == demo.saved()["flood_2023"]["ran_at"]


def test_saved_run_never_calls_a_model_even_for_automatic_languages(monkeypatch):
    monkeypatch.setattr(demo, "translate_alert", lambda *a: pytest.fail("no model calls for saved runs"))
    [a] = demo.saved_result("smoke_2020", "zh", "budget")["alerts"]
    assert a["lang"] == "en" and a["automatic"] is False


def test_handler_over_budget_returns_saved_run_not_an_error(monkeypatch):
    monkeypatch.setattr(budget, "over_budget", lambda: True)
    monkeypatch.setattr(demo, "run_monitor", lambda *a, **k: pytest.fail("agent must not run over budget"))
    r = ask_handler.handler(_event({"event": "heat_2022", "lang": "en"}), None)
    body = json.loads(r["body"])
    assert r["statusCode"] == 200 and body["source"] == "saved" and body["why"] == "budget"


def test_handler_rate_limit_returns_saved_run(monkeypatch):
    monkeypatch.setattr(budget, "over_budget", lambda: False)
    _agent_sends(monkeypatch)
    sources = [json.loads(ask_handler.handler(_event({"event": "heat_2022", "lang": "en"}), None)["body"])["why"]
               for _ in range(ask_handler.DEMO_REPLAYS_PER_IP_PER_HOUR + 1)]
    assert sources[:-1] == [None] * ask_handler.DEMO_REPLAYS_PER_IP_PER_HOUR and sources[-1] == "rate_limited"


@pytest.mark.parametrize("body,code", [({"event": "nope", "lang": "en"}, "unknown_event"),
                                       ({"event": "heat_2022", "lang": "xx"}, "invalid_lang")])
def test_handler_validates(body, code):
    r = ask_handler.handler(_event(body), None)
    assert r["statusCode"] == 400 and json.loads(r["body"])["error"] == code


def test_get_demo_has_events_cost_by_feature_and_budget_state(monkeypatch):
    for purpose, cost in (("monitor:CAZ159", 0.01), ("translate:ko", 0.001), ("ask:es", 0.002),
                          ("recovery-sam:debris", 0.0025), ("recovery-report:en", 0.006), ("pretalk:en", 0.001)):
        usage.log_extra("meta", "x", cost, purpose=purpose)
    r = api.handler({"routeKey": "GET /demo"}, None)
    body = json.loads(r["body"])
    assert r["statusCode"] == 200 and len(body["events"]) == 3 and body["over_budget"] is False
    assert body["cost"]["since"] == "2026-10-27" and body["cost"]["total_usd"] == 0.02
    assert body["cost"]["by_feature"] == {"alerts": 0.011, "ask": 0.002, "supervisor": 0.001,
                                          "recovery": 0.009, "other": 0.0}


def test_get_demo_still_works_when_the_usage_log_is_unreadable(monkeypatch):
    monkeypatch.setattr(demo, "cost_so_far", lambda: (_ for _ in ()).throw(RuntimeError("throttled")))
    body = json.loads(api.handler({"routeKey": "GET /demo"}, None)["body"])
    assert body["cost"] is None and len(body["events"]) == 3
