"""Offline tests for the supervisor view: checklist picked in code, talk guardrails, POST /pretalk."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest

from climateguard import config, pretalk, scenarios
from climateguard.handlers import ask as ask_handler
from climateguard.llm import ChatResult
from climateguard.store import get_store


@pytest.fixture(autouse=True)
def local(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "LOCAL_DIR", tmp_path)
    monkeypatch.setattr(config, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(config, "USAGE_LOG", tmp_path / "usage.jsonl")
    monkeypatch.setattr(config, "STORAGE", "local")


def _model_says(monkeypatch, text):
    monkeypatch.setattr(pretalk, "chat", lambda *a, **kw: ChatResult(
        text=text, model="m", prompt_tokens=1, completion_tokens=1, reasoning_tokens=0, cost_usd=0.001,
        cache_hit=False, raw={}))


def _ids(snap):
    return [i["id"] for i in pretalk.checklist(snap)]


def test_checklist_follows_todays_data():
    heat = scenarios.build("heatwave", "CAZ159")  # 108°F, 9 hours >= 95°F, Extreme Heat Warning, CA
    assert _ids(heat) == ["water", "shade80", "highheat95", "new_workers", "emergency"]
    assert "108°F (42°C)" in pretalk.render(pretalk.checklist(heat), "es")[1]["text"]
    smoke = scenarios.build("smoke", "CAZ159")  # PM2.5 AQI 178: masks help
    assert "smoke151" in _ids(smoke) and "air_no_masks" not in _ids(smoke)
    calm = scenarios.build("calm", "CAZ159")
    assert _ids(calm)[0] == "water" and _ids(calm)[-1] == "emergency" and "highheat95" not in _ids(calm)
    outside_ca = {**heat, "state": "MN"}
    assert "federal" in _ids(outside_ca) and "shade80" not in _ids(outside_ca)


def test_ozone_day_never_gets_mask_items():
    snap = scenarios.build("heatwave", "CAZ159")
    snap["summary"] = {**snap["summary"], "aqi_now": 160}
    snap["aqi"] = {"current": {"aqi": 160, "pollutant": "O3", "pm25_aqi": 40}, "forecast": []}
    assert "air_no_masks" in _ids(snap) and "smoke151" not in _ids(snap)


def test_talk_guardrails_fall_back_to_the_checklist(monkeypatch):
    snap = scenarios.build("heatwave", "CAZ159")
    _model_says(monkeypatch, "Hôm nay nóng tới 108°F. Bạn nên uống nước thường xuyên.")
    r = pretalk.build(snap, "vi")
    assert r["kind"] == "talk" and "108°F (42°C)" in r["talk"] and "Hãy uống nước" in r["talk"]
    _model_says(monkeypatch, "Watch for symptoms of heat stroke and take aspirin.")
    r = pretalk.build(snap, "en")
    assert r["kind"] == "checklist_only" and r["blocked"] == "medical_wording"
    assert r["talk"].startswith("Water:")
    _model_says(monkeypatch, "Wear an N95 mask today.")  # heat day, no smoke
    assert pretalk.build(snap, "en")["blocked"] == "mask_without_particles"


def test_unreviewed_languages_get_the_english_checklist_and_an_automatic_label(monkeypatch):
    _model_says(monkeypatch, "오늘은 108°F까지 오릅니다.")
    r = pretalk.build(scenarios.build("heatwave", "CAZ159"), "ko")
    assert r["automatic"] and r["checklist_lang"] == "en" and r["checklist"][0]["text"].startswith("Water:")


def test_handler_validates_and_rate_limits(monkeypatch):
    get_store().put_snapshot(scenarios.build("heatwave", "CAZ159"))
    _model_says(monkeypatch, "It is hot today.")

    def event(body, ip="1.2.3.4"):
        return {"routeKey": "POST /pretalk", "body": json.dumps(body), "requestContext": {"http": {"sourceIp": ip}}}
    r = ask_handler.handler(event({"zone": "caz159", "lang": "es"}), None)
    assert r["statusCode"] == 200 and json.loads(r["body"])["kind"] == "talk"
    assert json.loads(ask_handler.handler(event({"zone": "CAZ159", "lang": "fr"}), None)["body"])["error"] == "invalid_lang"
    monkeypatch.setattr(ask_handler, "PRETALK_PER_IP_PER_HOUR", 1)
    codes = [ask_handler.handler(event({"zone": "CAZ159", "lang": "en"}, ip="9.9.9.9"), None)["statusCode"] for _ in range(2)]
    assert codes == [200, 429]
