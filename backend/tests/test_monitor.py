"""Offline tests for the monitoring agent: guardrails, loop, decision log, DynamoDB paths."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest

from climateguard import alerts_store, cache, config, monitor, scenarios, usage
from climateguard.llm import ChatResult

GOOD = {"en": "Extreme heat today 12 PM to 8 PM. Drink water often and rest in the shade.",
        "es": "Calor extremo hoy de 12 a 8 de la tarde. Tome agua seguido y descanse en la sombra.",
        "vi": "Nắng nóng cực độ hôm nay từ 12 giờ trưa đến 8 giờ tối. Uống nước thường xuyên và nghỉ trong bóng mát."}


@pytest.fixture(autouse=True)
def local(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "LOCAL_DIR", tmp_path)
    monkeypatch.setattr(config, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(config, "USAGE_LOG", tmp_path / "usage.jsonl")
    monkeypatch.setattr(config, "STORAGE", "local")


def _run(scenario="heatwave"):
    return monitor.Run(zone="CAZ159", snapshot=scenarios.build(scenario, "CAZ159"))


def _alert(**over):
    return {"zone": "CAZ159", "hazard": "heat", "severity": "high", "messages_by_language": dict(GOOD),
            "reason": "test", **over}


# --- send_alert guardrails ---

def test_valid_alert_is_sent_and_recorded():
    run = _run()
    assert monitor.tool_send_alert(run, _alert())["sent"] is True
    assert alerts_store.recent_sent("CAZ159")[0]["severity"] == "high"


@pytest.mark.parametrize("lang,text", [
    ("en", "Watch for symptoms of heat stroke."),
    ("es", "Si tiene síntomas, tome un medicamento."),
    ("vi", "Nếu có triệu chứng hãy uống thuốc."),
])
def test_medical_wording_is_rejected(lang, text):
    msgs = dict(GOOD, **{lang: text})
    r = monitor.tool_send_alert(_run(), _alert(messages_by_language=msgs))
    assert r["sent"] is False and "medical" in r["rejected"]


def test_missing_language_and_too_long_rejected():
    r = monitor.tool_send_alert(_run(), _alert(messages_by_language={"en": "x", "es": "y"}))
    assert "missing" in r["rejected"]
    long = dict(GOOD, en="x" * 500)
    assert "characters" in monitor.tool_send_alert(_run(), _alert(messages_by_language=long))["rejected"]


def test_duplicate_rejected_but_escalation_allowed():
    run = _run()
    assert monitor.tool_send_alert(run, _alert(severity="high"))["sent"]
    assert "duplicate" in monitor.tool_send_alert(run, _alert(severity="high"))["rejected"]
    assert "duplicate" in monitor.tool_send_alert(run, _alert(severity="moderate"))["rejected"]
    assert monitor.tool_send_alert(run, _alert(severity="extreme"))["sent"]  # escalation
    assert monitor.tool_send_alert(run, _alert(hazard="smoke"))["sent"]  # different hazard


def test_daily_cap():
    run = _run()
    for hazard in ("heat", "smoke", "fog"):
        assert monitor.tool_send_alert(run, _alert(hazard=hazard))["sent"]
    assert "cap" in monitor.tool_send_alert(run, _alert(hazard="wind"))["rejected"]
    assert "cap" in monitor.tool_send_alert(run, _alert(hazard="wind", severity="moderate"))["rejected"]


def test_daily_cap_bypassed_only_by_higher_severity_than_all_sent_today():
    run = _run()
    for hazard, sev in (("heat", "moderate"), ("smoke", "high"), ("fog", "moderate")):
        assert monitor.tool_send_alert(run, _alert(hazard=hazard, severity=sev))["sent"]
    # "high" equals the highest already sent -> still capped
    assert "cap" in monitor.tool_send_alert(run, _alert(hazard="wind", severity="high"))["rejected"]
    # "extreme" beats every alert sent today -> goes through despite the cap
    assert monitor.tool_send_alert(run, _alert(hazard="wind", severity="extreme"))["sent"]
    # now extreme is the highest; nothing can bypass anymore
    assert "cap" in monitor.tool_send_alert(run, _alert(hazard="heat", severity="extreme"))["rejected"]


@pytest.mark.parametrize("summary", [
    {"active_alerts": ["Dense Fog Advisory"]},  # any NWS alert, even a mild one
    {"active_alerts": ["Special Weather Statement"]},
    {"aqi_now": 101},
    {"aqi_forecast_max": 101},
    {"aqi_now": 250, "active_alerts": []},
])
def test_prefilter_always_passes_nws_alerts_and_aqi_over_100(summary):
    assert monitor.risk_signals(summary)


def test_prefilter_blocks_quiet_data():
    assert monitor.risk_signals({"aqi_now": 100, "aqi_forecast_max": 100, "max_heat_index_f": 99,
                                 "hours_ge_95f": 0, "max_precip_prob": 59, "active_alerts": []}) == []


def test_tools_refuse_other_zones():
    run = _run()
    assert "error" in monitor.tool_get_forecast(run, {"zone": "CAZ999"})
    assert "error" in monitor.tool_send_alert(run, _alert(zone="MNZ060"))
    assert "error" not in monitor.tool_get_forecast(run, {"zone": "caz159"})


def test_forecast_tool_reports_local_times_and_air_temp_flags():
    r = monitor.tool_get_forecast(_run(), {"zone": "CAZ159"})
    assert len(r["hourly_local_time"]) == 24 and "heat index" in r["hourly_local_time"][0]
    assert "calosha_high_heat_95f" in r["summary"]["flags"]


# --- agent loop with a scripted fake model ---

def _tool_call(i, name, args):
    return {"id": f"call_{i}", "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}


class FakeModel:
    def __init__(self, script):
        self.script, self.seen = list(script), []

    def __call__(self, provider, model, messages, **kw):
        self.seen.append([dict(m) for m in messages])
        step = self.script.pop(0)
        msg = {"content": step.get("content", ""), "reasoning_content": "SECRET REASONING",
               "tool_calls": step.get("tool_calls")}
        return ChatResult(text=step.get("content", ""), model=model, prompt_tokens=100, completion_tokens=50,
                          reasoning_tokens=40, cost_usd=0.001, cache_hit=False,
                          raw={"choices": [{"message": msg, "finish_reason": "stop"}]})


def test_agent_sends_and_logs_decision(monkeypatch):
    fake = FakeModel([
        {"tool_calls": [_tool_call(1, "get_nws_alerts", {"zone": "CAZ159"}),
                        _tool_call(2, "get_recent_alerts_sent", {"zone": "CAZ159"})]},
        {"tool_calls": [_tool_call(3, "search_safety_guidance", {"query": "heat water shade"})]},
        {"tool_calls": [_tool_call(4, "send_alert", _alert(severity="extreme"))]},
        {"content": "SENT: Extreme Heat Warning with 108F and no prior alert."},
    ])
    monkeypatch.setattr(monitor, "chat", fake)
    d = monitor.run_monitor("CAZ159", scenarios.build("heatwave", "CAZ159"))
    assert d["action"] == "sent" and d["reason"].startswith("Extreme Heat Warning")
    assert d["model_calls"] == 4 and d["cost_usd"] == pytest.approx(0.004)
    assert [t["tool"] for t in d["tools"]][-1] == "send_alert"
    # reasoning is never fed back into the conversation
    assert all("reasoning_content" not in m for convo in fake.seen for m in convo)
    assert alerts_store.recent_decisions("CAZ159")[-1]["action"] == "sent"


def test_agent_skip_when_model_declines(monkeypatch):
    # skipping is allowed here because the heat warning was already alerted (otherwise it is sent back)
    alerts_store.record_sent("CAZ159", "heat", "extreme", GOOD, "earlier")
    monkeypatch.setattr(monitor, "chat", FakeModel([{"content": "SKIPPED: already alerted."}]))
    d = monitor.run_monitor("CAZ159", scenarios.build("heatwave", "CAZ159"))
    assert d["action"] == "skipped" and d["reason"] == "already alerted."


def test_prefilter_skips_without_model_call(monkeypatch):
    monkeypatch.setattr(monitor, "chat", lambda *a, **k: pytest.fail("model must not be called"))
    d = monitor.run_monitor("CAZ159", scenarios.build("calm", "CAZ159"))
    assert d["action"] == "skipped" and d["model_calls"] == 0


def test_step_limit_and_errors_are_logged(monkeypatch):
    loop = [{"tool_calls": [_tool_call(i, "get_aqi", {"zone": "CAZ159"})]} for i in range(monitor.MAX_STEPS)]
    monkeypatch.setattr(monitor, "chat", FakeModel(loop))
    assert "step limit" in monitor.run_monitor("CAZ159", scenarios.build("smoke", "CAZ159"))["reason"]

    def boom(*a, **k):
        raise TimeoutError("Baseten timed out")
    monkeypatch.setattr(monitor, "chat", boom)
    d = monitor.run_monitor("CAZ159", scenarios.build("smoke", "CAZ159"))
    assert d["action"] == "error" and "timed out" in d["reason"]


# --- DynamoDB code paths (fake table) ---

class FakeTable:
    def __init__(self):
        self.items = {}

    def _k(self, item):
        return tuple(sorted((k, v) for k, v in item.items() if k in ("day", "sk", "key", "zone")))

    def put_item(self, Item):
        self.items[self._k(Item)] = dict(Item)

    def get_item(self, Key):
        return {"Item": self.items[self._k(Key)]} if self._k(Key) in self.items else {}

    def scan(self, **kw):
        return {"Items": list(self.items.values())}

    def query(self, KeyConditionExpression):
        return {"Items": list(self.items.values())}  # single city in this test


def test_dynamodb_usage_cache_and_alerts(monkeypatch):
    monkeypatch.setattr(config, "STORAGE", "dynamodb")
    tables = {"usage": FakeTable(), "cache": FakeTable(), "alerts": FakeTable()}
    monkeypatch.setattr(usage, "_table", lambda: tables["usage"])
    monkeypatch.setattr(cache, "_table", lambda: tables["cache"])
    monkeypatch.setattr(alerts_store, "_table", lambda: tables["alerts"])

    usage.log_call("baseten", "meta-models/muse-spark-open-1026", 1000, 500)
    usage.log_call("baseten", "meta-models/muse-spark-open-1026", 1000, 500, cache_hit=True)
    t = usage.totals()[("baseten", "meta-models/muse-spark-open-1026")]
    assert t["calls"] == 2 and t["cache_hits"] == 1 and t["cost_usd"] == pytest.approx(0.003375)

    cache.put("k1", {"a": 1}, ttl=60)
    assert cache.get("k1", ttl=60) == {"a": 1}
    cache.put("k2", {"a": 2}, ttl=-1)  # already expired: DynamoDB TTL is lazy, so reads must check
    assert cache.get("k2", ttl=60) is None

    alerts_store.record_sent("CAZ159", "heat", "high", GOOD, "test")
    [row] = alerts_store.recent_sent("CAZ159")
    assert row["hazard"] == "heat" and row["messages"]["vi"] == GOOD["vi"]


def test_run_deadline_stops_a_slow_agent_and_logs_an_error(monkeypatch):
    monkeypatch.setattr(config, "AGENT_RUN_DEADLINE_S", -1.0)  # already over the limit before step 1
    monkeypatch.setattr(monitor, "chat", lambda *a, **k: pytest.fail("no model call after the deadline"))
    d = monitor.run_monitor("CAZ159", scenarios.build("heatwave", "CAZ159"))
    assert d["action"] == "error" and "time limit" in d["reason"] and d["model_calls"] == 0


# --- an active official Warning may not be skipped (eval case hard_warning_vs_mild_data) ---

def _warning_snapshot(ends_in=30, peak=82, event="Extreme Heat Warning", severity="Severe"):
    """An official warning whose own text says 110, over data that only shows `peak` (82F by default)."""
    from datetime import datetime
    from zoneinfo import ZoneInfo
    tz = ZoneInfo("America/Los_Angeles")
    parts = {"hours": scenarios.hours(tz, scenarios.heat_curve(peak), lambda h: 40),
             "aqi": scenarios.aqi(tz, 40, [40, 40]),
             "alerts": [scenarios.nws_alert(tz, event, severity, ends_in, f"{event} in effect",
                                            "Dangerously hot conditions with temperatures up to 110 expected.",
                                            "Stay cool.")]}
    return scenarios.assemble("CAZ159", parts, "conflict")


NO_NUMBERS = {"en": "An official Extreme Heat Warning is in effect. Drink water often and rest in the shade.",
              "es": "Hay un Aviso oficial de calor extremo. Tome agua seguido y descanse en la sombra.",
              "vi": "Có Cảnh báo nắng nóng gay gắt chính thức. Hãy uống nước thường xuyên và nghỉ trong bóng râm."}


def test_agent_that_skips_an_active_warning_is_sent_back_and_alerts(monkeypatch):
    fake = FakeModel([
        {"content": "SKIPPED: the data shows only 82F, milder than the warning text."},
        {"tool_calls": [_tool_call(1, "send_alert", _alert(severity="high", messages_by_language=NO_NUMBERS))]},
        {"content": "SENT: official Extreme Heat Warning, numbers left out because the data disagrees."},
    ])
    monkeypatch.setattr(monitor, "chat", fake)
    d = monitor.run_monitor("CAZ159", _warning_snapshot())
    assert d["action"] == "sent" and d["model_calls"] == 3
    nudge = fake.seen[1][-1]
    assert nudge["role"] == "user" and "Extreme Heat Warning" in nudge["content"] and "leave numbers out" in nudge["content"]
    assert alerts_store.recent_sent("CAZ159")[0]["messages"]["en"] == NO_NUMBERS["en"]


def test_agent_is_sent_back_at_most_twice(monkeypatch):
    fake = FakeModel([{"content": "SKIPPED: milder data."}] * 3)
    monkeypatch.setattr(monitor, "chat", fake)
    d = monitor.run_monitor("CAZ159", _warning_snapshot())
    assert d["action"] == "skipped" and d["model_calls"] == 1 + monitor.MAX_WARNING_NUDGES


def test_temperatures_are_left_out_when_the_data_disagrees_with_the_warning():
    run = monitor.Run(zone="CAZ159", snapshot=_warning_snapshot())
    for lang, text in (("en", "Extreme Heat Warning. Temperatures up to 110°F today."),
                       ("es", "Aviso de calor extremo. Hasta 110 grados hoy."),
                       ("vi", "Cảnh báo nắng nóng. Nhiệt độ lên tới 110 độ hôm nay.")):
        r = monitor.tool_send_alert(run, _alert(messages_by_language=dict(NO_NUMBERS, **{lang: text})))
        assert r["sent"] is False and "leave temperatures out" in r["rejected"], lang
    assert monitor.tool_send_alert(run, _alert(messages_by_language=NO_NUMBERS))["sent"] is True


def test_temperatures_are_fine_when_the_data_shows_the_heat():
    run = monitor.Run(zone="CAZ159", snapshot=_warning_snapshot(peak=108))
    msgs = dict(NO_NUMBERS, en="Extreme Heat Warning. Temperatures up to 108°F today. Drink water often.")
    assert monitor.tool_send_alert(run, _alert(messages_by_language=msgs))["sent"] is True


def test_what_counts_as_an_unalerted_warning():
    def missing(snap, **kw):
        return [a["event"] for a in monitor.unalerted_warnings(monitor.Run(zone="CAZ159", snapshot=snap, **kw))]

    assert missing(_warning_snapshot()) == ["Extreme Heat Warning"]
    assert missing(_warning_snapshot(event="Flood Warning")) == ["Flood Warning"]
    assert missing(_warning_snapshot(event="Heat Advisory", severity="Minor")) == []  # only Warnings are required
    assert missing(_warning_snapshot(ends_in=-3)) == []  # expired, still in the feed
    assert missing(_warning_snapshot(ends_in=2)) == []  # ends within 3 h and the data no longer shows heat
    assert missing(_warning_snapshot(ends_in=2, peak=104)) == ["Extreme Heat Warning"]  # heat is coming back
    run = monitor.Run(zone="CAZ159", snapshot=_warning_snapshot())
    run.sent.append({"hazard": "heat", "severity": "moderate", "messages": NO_NUMBERS})
    assert monitor.unalerted_warnings(run) == []  # this run already alerted it
    alerts_store.record_sent("CAZ159", "heat", "high", NO_NUMBERS, "earlier")
    assert missing(_warning_snapshot()) == []  # already alerted in the last 24 h at its severity (dedup)
    assert missing(_warning_snapshot(severity="Extreme")) == ["Extreme Heat Warning"]  # worse than what was sent


def test_short_fuse_warnings_never_become_required(monkeypatch):
    monkeypatch.setattr(monitor, "chat", lambda *a, **k: pytest.fail("a lone Tornado Warning must not run the agent"))
    d = monitor.run_monitor("MNZ060", scenarios.build("tornado_warning", "MNZ060"))
    assert d["action"] == "skipped" and d["model_calls"] == 0
