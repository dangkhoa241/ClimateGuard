"""Offline tests for Ask: the symptom guardrail, answer checks, and the POST /ask handler."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest

from climateguard import ask, config, scenarios
from climateguard.handlers import ask as ask_handler
from climateguard.languages import LANGS
from climateguard.llm import ChatResult
from climateguard.store import get_store


@pytest.fixture(autouse=True)
def local(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "LOCAL_DIR", tmp_path)
    monkeypatch.setattr(config, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(config, "USAGE_LOG", tmp_path / "usage.jsonl")
    monkeypatch.setattr(config, "STORAGE", "local")


def _store(scenario="heatwave"):
    snap = scenarios.build(scenario, "CAZ159")
    get_store().put_snapshot(snap)
    return snap


def _model_says(monkeypatch, text, seen=None):
    def fake(provider, model, messages, **kw):
        if seen is not None:
            seen.append({"messages": messages, **kw})
        return ChatResult(text=text, model=model, prompt_tokens=10, completion_tokens=10, reasoning_tokens=0,
                          cost_usd=0.0001, cache_hit=False, raw={})
    monkeypatch.setattr(ask, "chat", fake)


SYMPTOM_QUESTIONS = [
    ("en", "My coworker is dizzy and has a headache, what should I do?"),
    ("en", "Can I take ibuprofen for the heat?"),
    ("es", "Mi esposo tiene náuseas y calambres después de trabajar"),
    ("es", "¿Qué medicina tomo para el golpe de calor?"),
    ("vi", "Con tôi bị chóng mặt và buồn nôn"),
    ("vi", "Tôi đang mang thai, có nên làm việc ngoài trời không?"),
    ("zh", "我头晕，是中暑了吗？"),
    ("tl", "Nahihilo ako at masakit ang ulo ko"),
    ("ko", "어지러워요. 열사병인가요?"),
    ("ar", "أشعر بدوخة وصداع"),
]
SAFE_QUESTIONS = [
    ("en", "Is it safe to work outside this afternoon?"),
    ("es", "¿Va a hacer calor mañana?"),
    ("vi", "Hôm nay có nắng nóng không?"),
    ("zh", "明天会很热吗？"),
    ("ko", "오늘 밖에서 일해도 되나요?"),
    ("en", "Will the air quality be bad tomorrow?"),
]


@pytest.mark.parametrize("lang,question", SYMPTOM_QUESTIONS)
def test_symptom_questions_get_the_fixed_answer_without_a_model_call(monkeypatch, lang, question):
    monkeypatch.setattr(ask, "chat", lambda *a, **k: pytest.fail("model must not be called"))
    r = ask.answer(question, lang, "CAZ159")
    assert r == {"kind": "symptom", "answer": ask.SYMPTOM_ANSWER[lang]}
    assert "911" in r["answer"]


@pytest.mark.parametrize("lang,question", SAFE_QUESTIONS)
def test_ordinary_questions_are_not_mistaken_for_symptoms(lang, question):
    assert not ask.SYMPTOM_QUESTION.search(question)


def test_fixed_answers_exist_in_every_language():
    assert set(ask.SYMPTOM_ANSWER) == set(ask.FALLBACK_ANSWER) == set(LANGS)


def test_answer_is_grounded_in_live_data_and_guidance(monkeypatch):
    _store()
    seen = []
    _model_says(monkeypatch, "Today it will reach 108°F. Work early, drink water, rest in shade.", seen)
    r = ask.answer("Is it safe to work outside today?", "en", "CAZ159")
    assert r["kind"] == "answer" and "108°F" in r["answer"]
    assert r["sources"] and r["data_time_local"] and "Extreme Heat Warning" in r["nws_alerts"]
    call = seen[0]
    assert call["deadline_s"] == ask.CALL_DEADLINE_S and call["max_tokens"] == ask.MAX_ANSWER_TOKENS
    user = call["messages"][1]["content"]
    assert "Extreme Heat Warning" in user and "GUIDANCE" in user and '"masks_help": false' in user


def test_vietnamese_answers_get_the_reviewed_wording_rules(monkeypatch):
    _store()
    seen = []
    _model_says(monkeypatch, "Hôm nay nắng nóng.", seen)
    ask.answer("Hôm nay có nắng nóng không?", "vi", "CAZ159")
    system = seen[0]["messages"][0]["content"]
    assert "Vietnamese" in system and "Cảnh giác" in system and "rạng sáng" in system


def test_medical_wording_in_the_answer_is_replaced(monkeypatch):
    _store()
    _model_says(monkeypatch, "If you feel symptoms of heat stroke, take aspirin.")
    r = ask.answer("Is it hot today?", "en", "CAZ159")
    assert r["kind"] == "symptom" and r["blocked"] == "medical_wording" and r["answer"] == ask.SYMPTOM_ANSWER["en"]


def test_mask_advice_without_particles_is_blocked(monkeypatch):
    _store("heatwave")  # no smoke
    _model_says(monkeypatch, "Wear an N95 mask outside today.")
    r = ask.answer("Should I protect myself outside?", "en", "CAZ159")
    assert r["kind"] == "fallback" and r["blocked"] == "mask_without_particles"
    _store("smoke")  # smoke: masks help
    _model_says(monkeypatch, "Smoke is heavy. If you must go out, wear an N95 mask.")
    assert ask.answer("Should I protect myself outside?", "en", "CAZ159")["kind"] == "answer"


def test_model_failure_and_budget_give_the_fallback(monkeypatch):
    _store()

    def boom(*a, **k):
        raise TimeoutError("slow")
    monkeypatch.setattr(ask, "chat", boom)
    r = ask.answer("Is it hot today?", "es", "CAZ159")
    assert r["kind"] == "fallback" and r["answer"] == ask.FALLBACK_ANSWER["es"]
    monkeypatch.setattr(ask.budget, "over_budget", lambda: True)
    assert ask.answer("Is it hot today?", "en", "CAZ159")["reason"] == "budget"


def test_stale_snapshot_is_refreshed_on_demand(monkeypatch):
    snap = _store()
    stale = {**snap, "generated_at": "2020-01-01T00:00:00+00:00"}
    get_store().put_snapshot(stale)
    built = []
    monkeypatch.setattr(ask.nws, "get_zone_alerts", lambda rec: [])
    monkeypatch.setattr(ask.snapshot, "build_snapshot", lambda rec, alerts, prev=None: built.append(alerts) or snap)
    assert ask.zone_snapshot("CAZ159") is snap and built == [[]]


def _event(body, ip="1.2.3.4"):
    return {"routeKey": "POST /ask", "body": json.dumps(body), "requestContext": {"http": {"sourceIp": ip}}}


def test_handler_validates_and_rate_limits(monkeypatch):
    _store()
    _model_says(monkeypatch, "Hot today.")
    ok = {"question": "Is it hot?", "lang": "en", "zone": "caz159"}
    assert ask_handler.handler(_event(ok), None)["statusCode"] == 200
    for bad, code in (({**ok, "lang": "fr"}, "invalid_lang"), ({**ok, "zone": "x"}, "unknown_zone"),
                      ({**ok, "question": " "}, "invalid_question"),
                      ({**ok, "question": "x" * 501}, "invalid_question")):
        r = ask_handler.handler(_event(bad), None)
        assert r["statusCode"] == 400 and json.loads(r["body"])["error"] == code
    monkeypatch.setattr(ask_handler, "ASK_PER_IP_PER_HOUR", 2)
    codes = [ask_handler.handler(_event(ok, ip="9.9.9.9"), None)["statusCode"] for _ in range(3)]
    assert codes == [200, 200, 429]


def test_mask_question_on_a_clean_or_ozone_day_gets_the_fixed_note(monkeypatch):
    _store("heatwave")  # no particles
    _model_says(monkeypatch, "Hôm nay không khí ở mức tốt.")
    r = ask.answer("Tôi có cần đeo khẩu trang không?", "vi", "CAZ159")
    assert r["kind"] == "answer" and r["answer"].endswith(ask.MASK_NOTE["vi"])
    _store("smoke")  # particles: no note, the model's own (allowed) advice stands
    _model_says(monkeypatch, "Smoke is heavy. Wear an N95 mask if you go out.")
    assert ask.MASK_NOTE["en"] not in ask.answer("Do I need a mask?", "en", "CAZ159")["answer"]


@pytest.mark.parametrize("question,topic", [
    ("Ngày mai chất lượng không khí thế nào?", "air quality aqi smoke"),
    ("¿Hay riesgo de inundación esta noche?", "flood water"),
    ("明天很热吗？", "heat hot temperature"),
    ("Is it safe to work outside?", "outdoor workers work"),
])
def test_non_english_questions_find_the_right_guidance(question, topic):
    snap = scenarios.build("calm", "CAZ159")
    assert topic in ask._guidance_query(question, snap)


def test_mask_note_in_every_language():
    from climateguard import guardrails
    assert set(ask.MASK_NOTE) == set(LANGS) and all(guardrails.mentions_mask(t) for t in ask.MASK_NOTE.values())
