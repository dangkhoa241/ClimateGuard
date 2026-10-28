"""Offline tests for Phase 3.5b: real-event replays, replay/eval isolation, eval scoring,
daily stats and the public decision-history API."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]

import pytest

from climateguard import alerts_store, config, monitor, notify, replays, stats, zones
from climateguard.handlers import api, collect as collect_mod
from climateguard.llm import ChatResult


@pytest.fixture(autouse=True)
def local(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "LOCAL_DIR", tmp_path)
    monkeypatch.setattr(config, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(config, "USAGE_LOG", tmp_path / "usage.jsonl")
    monkeypatch.setattr(config, "STORAGE", "local")
    monkeypatch.setattr(config, "NOTIFY_MODE", "dryrun")


# --- replay data (built from public archives, committed) ---

def test_three_real_events_are_available():
    assert replays.available() == ["flood_2023", "heat_2022", "smoke_2020"]
    for c in replays.catalog():
        assert c["banner"].startswith("REPLAY of a real event") and c["moments"]
        assert "example" in c["story"].lower()  # Maria is always labeled as an example person


def test_heat_2022_record_day_matches_the_archive():
    s = replays.snapshot_for("heat_2022", "record_day_morning")
    assert s["zone"] == "CAZ159" and s["replay"]["at_local"].startswith("2022-09-06T07:00")
    assert s["summary"]["max_temp_f"] >= 110 and s["summary"]["hours_ge_95f"] >= 8
    [a] = s["alerts"]
    assert a["event"] == "Excessive Heat Warning" and a["ends"].startswith("2022-09-09T20:00")
    assert "dangerously hot" in a["description"].lower()  # the real NWS wording
    assert "/O." not in a["description"]  # VTEC/zone header lines stripped


def test_watch_disappears_once_upgraded_to_warning():
    events = [a["event"] for a in replays.snapshot_for("heat_2022", "warning_starts")["alerts"]]
    assert events == ["Excessive Heat Warning"]


def test_quiet_moments_have_no_risk_signals():
    for event, moment in (("heat_2022", "after"), ("smoke_2020", "improving")):
        assert monitor.risk_signals(replays.snapshot_for(event, moment)["summary"]) == []


def test_flood_2023_progression():
    watch = replays.snapshot_for("flood_2023", "watch")
    night = replays.snapshot_for("flood_2023", "warning_night")
    assert [a["event"] for a in watch["alerts"]] == ["Flood Watch"]
    assert "Flood Warning" in [a["event"] for a in night["alerts"]]
    assert any("Bear Creek" in a["description"] for a in night["alerts"])
    assert all(a["hazard"] == "flood" for a in night["alerts"])


def test_unknown_replay_or_moment_is_an_error():
    with pytest.raises(KeyError):
        replays.snapshot_for("heat_1999", "x")
    with pytest.raises(KeyError):
        replays.snapshot_for("heat_2022", "nope")


# --- isolation: replays/evals never email and never enter live history ---

class Scripted:
    def __init__(self, steps):
        self.steps = list(steps)

    def __call__(self, provider, model, messages, **kw):
        step = self.steps.pop(0)
        msg = {"content": step.get("content", ""), "tool_calls": step.get("tool_calls")}
        return ChatResult(text=step.get("content", ""), model=model, prompt_tokens=10, completion_tokens=5,
                          reasoning_tokens=0, cost_usd=0.001, cache_hit=False,
                          raw={"choices": [{"message": msg, "finish_reason": "stop"}]})


def _send(zone):
    args = {"zone": zone, "hazard": "heat", "severity": "extreme", "reason": "r",
            "messages_by_language": {"en": "Extreme heat today.", "es": "Calor extremo hoy.",
                                     "vi": "Nắng nóng cực độ hôm nay."}}
    return {"tool_calls": [{"id": "c1", "type": "function",
                            "function": {"name": "send_alert", "arguments": json.dumps(args)}}]}


def test_replay_run_is_isolated_and_never_emails(monkeypatch):
    seen = []
    script = Scripted([_send("CAZ159"), {"content": "SENT: replay heat"}])
    monkeypatch.setattr(monitor, "chat", lambda *a, **k: seen.append(a[2][1]["content"]) or script(*a, **k))
    monkeypatch.setattr(notify, "deliver", lambda *a, **k: pytest.fail("replays must never email"))
    d = monitor.run_monitor("CAZ159", replays.snapshot_for("heat_2022", "warning_issued"))
    assert d["action"] == "sent" and d["replay"] == {"event": "heat_2022", "moment": "warning_issued"}
    assert alerts_store.recent_decisions("REPLAY-heat_2022") and not alerts_store.recent_decisions("CAZ159")
    assert alerts_store.recent_sent("REPLAY-heat_2022") and not alerts_store.recent_sent("CAZ159")
    assert "REPLAY of a real past event" in seen[0] and "2022-09-01 10:00" in seen[0]  # agent told the replay time


def test_eval_namespace_is_isolated(monkeypatch):
    monkeypatch.setattr(monitor, "chat", Scripted([_send("CAZ159"), {"content": "SENT: x"}]))
    monkeypatch.setattr(notify, "deliver", lambda *a, **k: pytest.fail("evals must never email"))
    from climateguard import scenarios
    monitor.run_monitor("CAZ159", scenarios.build("heatwave"), namespace="EVAL-x")
    assert alerts_store.recent_sent("EVAL-x") and not alerts_store.recent_sent("CAZ159")


# --- eval scoring ---

def test_eval_scoring():
    from run_eval import rejection_kind, score_step
    sent = {"action": "sent", "model_calls": 4, "sent": [
        {"hazard": "heat", "severity": "extreme", "messages": {"en": "Drink water.", "es": "a", "vi": "Uống nước."}}]}
    assert all(score_step({"send": True, "hazards": {"heat"}, "severity": {"high", "extreme"}}, sent, None).values())
    assert not score_step({"send": True, "hazards": {"smoke"}}, sent, None)["hazards"]
    assert not score_step({"no_repeat": {"heat"}}, sent, None)["no_repeat"]
    prev = {"sent": [{"hazard": "heat", "severity": "moderate"}]}
    assert score_step({"send": True, "escalate": "heat"}, sent, prev)["escalate"]
    assert not score_step({"send": True, "escalate": "heat"}, sent, {"sent": [{"hazard": "heat", "severity": "extreme"}]})["escalate"]
    bad = {"action": "sent", "sent": [{"hazard": "heat", "severity": "high", "messages": {"en": "take aspirin"}}]}
    assert not score_step({}, bad, None)["no_medical_wording"]
    assert rejection_kind("duplicate: a high heat alert was already sent") == "duplicate"
    # categories must match the real rejection messages from monitor.validate_alert
    from climateguard import scenarios
    run = monitor.Run(zone="CAZ159", snapshot=scenarios.build("heatwave"))
    base = {"zone": "CAZ159", "hazard": "heat", "severity": "high", "reason": "r",
            "messages_by_language": {"en": "Heat.", "es": "Calor.", "vi": "Nóng."}}
    medical = monitor.validate_alert(run, {**base, "messages_by_language": {**base["messages_by_language"],
                                                                            "es": "Si tiene síntomas"}})
    missing = monitor.validate_alert(run, {**base, "messages_by_language": {"en": "Heat."}})
    long = monitor.validate_alert(run, {**base, "messages_by_language": {**base["messages_by_language"], "en": "x" * 500}})
    assert [rejection_kind(r) for r in (medical, missing, long)] == ["medical_wording", "missing_language", "too_long"]


def test_eval_cases_are_well_formed():
    from eval_cases import CASES
    assert len(CASES) >= 20 and len({c["id"] for c in CASES}) == len(CASES)
    assert {c["kind"] for c in CASES} == {"real", "edge"}
    for c in CASES:
        for make, expect in c["steps"]:
            assert make()["zone"] and set(expect) <= {"send", "hazards", "severity", "no_repeat", "escalate",
                                                      "zero_calls"}


def test_missing_diacritics_rejected_so_the_agent_rewrites():
    from climateguard import scenarios
    from run_eval import rejection_kind
    run = monitor.Run(zone="CAZ159", snapshot=scenarios.build("heatwave"))
    ok = {"en": "Extreme heat today. Drink water.", "es": "Calor extremo hoy. Tome agua y descanse en la sombra.",
          "vi": "Nắng nóng cực độ hôm nay. Uống nước thường xuyên."}
    base = {"zone": "CAZ159", "hazard": "heat", "severity": "high", "reason": "r"}
    assert monitor.validate_alert(run, {**base, "messages_by_language": ok}) is None
    vi_ascii = monitor.validate_alert(run, {**base, "messages_by_language": {**ok, "vi": "Canh bao Ngap Lut co hieu luc"}})
    es_ascii = monitor.validate_alert(run, {**base, "messages_by_language": {
        **ok, "es": "Hay Aviso de Inundacion hasta las 11:15 de esta noche lunes y el rio seguira crecido"}})
    es_short = monitor.validate_alert(run, {**base, "messages_by_language": {**ok, "es": "Calor hoy. Tome agua."}})
    assert rejection_kind(vi_ascii) == rejection_kind(es_ascii) == "missing_diacritics"
    assert es_short is None  # Spanish can legitimately have no accents...
    fine = "Calor extremo hoy de 12 a 8 de la tarde. Tome agua seguido y descanse en la sombra."
    assert monitor.validate_alert(run, {**base, "messages_by_language": {**ok, "es": fine}}) is None


# --- stats + decision-history API ---

def test_stats_summarize_and_record():
    result = {"zones": 2, "changed": ["CAZ159"], "failed": {}, "decisions": {
        "CAZ159": {"action": "sent", "reason": "heat", "cost_usd": 0.01, "alerts_sent": 1},
        "CAZ303": {"action": "skipped", "reason": "pre-filter: no risk signals", "cost_usd": 0}}}
    c = stats.summarize_run(result)
    assert c["zone_checks"] == 2 and c["agent_runs"] == 1 and c["prefilter_skips"] == 1 and c["alerts_sent"] == 1
    stats.record(c)
    stats.record(stats.summarize_run({"zones": 2, "changed": [], "failed": {}, "decisions": {}}))
    t = stats.totals(stats.recent(1))
    assert t["collector_runs"] == 2 and t["zone_checks"] == 4 and t["model_cost_usd"] == 0.01


def test_decisions_api_shows_live_only_and_is_sanitized(monkeypatch):
    monkeypatch.setattr(monitor, "chat", Scripted([_send("CAZ159"), {"content": "SENT: live heat"}]))
    monkeypatch.setattr(notify, "deliver", lambda *a, **k: {"channel": "dryrun"})
    from climateguard import scenarios
    monitor.run_monitor("CAZ159", scenarios.build("heatwave"))                    # live decision
    monitor.run_monitor("CAZ303", scenarios.build("calm", "CAZ303"))              # live pre-filter skip
    monkeypatch.setattr(monitor, "chat", Scripted([{"content": "SKIPPED: replay"}]))
    monitor.run_monitor("CAZ159", replays.snapshot_for("heat_2022", "record_day_morning"))  # replay: excluded
    stats.record({"collector_runs": 1, "zone_checks": 2})
    r = api.handler({"routeKey": "GET /decisions", "queryStringParameters": {"days": "2"}}, None)
    body = json.loads(r["body"])
    assert r["statusCode"] == 200 and len(body["decisions"]) == 2
    assert {d["action"] for d in body["decisions"]} == {"sent", "skipped"}
    live = next(d for d in body["decisions"] if d["action"] == "sent")
    assert live["place"] == "Stockton, CA" and live["alerts"][0]["hazard"] == "heat"
    assert set(live) == {"ts", "zone", "place", "action", "reason", "signals", "tools", "alerts", "model_calls",
                         "cost_usd"}
    assert body["totals"]["collector_runs"] == 1 and {z["zone"] for z in body["zones"]} == {"CAZ159", "CAZ303"}
    one = json.loads(api.handler({"routeKey": "GET /decisions", "queryStringParameters": {"zone": "caz303"}},
                                 None)["body"])
    assert [d["zone"] for d in one["decisions"]] == ["CAZ303"]
    assert api.handler({"routeKey": "GET /decisions", "queryStringParameters": {"days": "x"}}, None)["statusCode"] == 400


def test_collector_records_daily_stats(monkeypatch):
    from climateguard import subscriptions
    from climateguard.sources import nws
    monkeypatch.setattr(nws, "get_national_alerts", lambda: [])
    monkeypatch.setattr(subscriptions, "refresh_confirmed", lambda: [])
    monkeypatch.setattr(zones, "monitored", lambda: [])
    collect_mod.handler({}, None)
    assert stats.totals(stats.recent(1))["collector_runs"] == 1
