"""Offline tests for Ask: the symptom guardrail, answer checks, and the POST /ask handler."""
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest

from climateguard import ask, config, scenarios, timeref
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
    monkeypatch.setattr(ask.places, "find", lambda question, lang, snap: None)  # offline: no web search


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
    assert (r["kind"], r["answer"]) == ("symptom", ask.SYMPTOM_ANSWER[lang]) and "model" not in r["timings_ms"]
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
    assert call["deadline_s"] == ask.CALL_DEADLINE_S and call["max_tokens"] == ask.MAX_ANSWER_TOKENS[ask.ASK_REASONING_EFFORT]
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


def _translate_event(body, ip="1.2.3.4"):
    return {"routeKey": "POST /translate", "body": json.dumps(body),
            "requestContext": {"http": {"sourceIp": ip}}}


def test_translate_retry_only_translates_a_recent_alert(monkeypatch):
    sent = {"ts": "2026-10-30T12:00:00+00:00", "hazard": "heat",
            "messages": {"en": "Heat alert."}}
    monkeypatch.setattr(ask_handler.alerts_store, "recent_sent", lambda zone, hours: [sent])
    monkeypatch.setattr(ask_handler, "translate_alert",
                        lambda text, lang, **kwargs: (f"{lang}: {text}", True))
    body = {"zone": "CAZ159", "sent_at": sent["ts"], "hazard": "heat", "lang": "vi"}
    response = ask_handler.handler(_translate_event(body), None)
    assert response["statusCode"] == 200 and json.loads(response["body"]) == {
        "text": "vi: Heat alert.", "lang": "vi",
    }

    sent["ts"] = "different"
    response = ask_handler.handler(_translate_event(body), None)
    assert response["statusCode"] == 404 and json.loads(response["body"])["error"] == "unknown_alert"


def test_translate_retry_reports_failure_and_is_rate_limited(monkeypatch):
    sent = {"ts": "2026-10-30T12:00:00+00:00", "hazard": "heat",
            "messages": {"en": "Heat alert."}}
    monkeypatch.setattr(ask_handler.alerts_store, "recent_sent", lambda zone, hours: [sent])
    monkeypatch.setattr(ask_handler, "translate_alert", lambda text, lang, **kwargs: (text, False))
    body = {"zone": "CAZ159", "sent_at": sent["ts"], "hazard": "heat", "lang": "vi"}
    failed = ask_handler.handler(_translate_event(body), None)
    assert failed["statusCode"] == 502
    monkeypatch.setattr(ask_handler, "TRANSLATE_PER_IP_PER_HOUR", 1)
    first = ask_handler.handler(_translate_event(body, ip="9.9.9.9"), None)
    limited = ask_handler.handler(_translate_event(body, ip="9.9.9.9"), None)
    assert first["statusCode"] == 502 and limited["statusCode"] == 429

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


@pytest.mark.parametrize("question,model_text,want_211", [
    ("Where is the nearest cooling center?", "It is 108°F today. Stay in air conditioning.", True),
    ("Ở đâu có trung tâm làm mát?", "Hôm nay nóng tới 108°F.", True),
    ("¿Hay refugio cerca?", "Hoy hace mucho calor. Llame al 211 para saber más.", True),
    ("Gần đây có chỗ nào mát để nghỉ không?", "Tôi không biết chỗ mát cụ thể gần bạn.", True),
    ("Can my family stay somewhere tonight?", "Hot tonight.\n[211]", True),  # the model's marker
    ("Will there be a tornado next month?", "I don't know. Call 211 for more help.", False),
    ("Is it hot today?", "Yes, up to 108°F. Drink water often.", False),
])
def test_211_is_a_fixed_sentence(monkeypatch, question, model_text, want_211):
    _store()
    _model_says(monkeypatch, model_text)
    lang = "vi" if model_text.startswith(("Hôm", "Tôi")) else "es" if "¿" in question else "en"
    text = ask.answer(question, lang, "CAZ159")["answer"]
    assert text.endswith(ask.HELP_211[lang]) == want_211
    assert "[211]" not in text and text.count("211") == int(want_211)  # the model's own 211 sentence is gone
    assert not text.startswith("\n")


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


def test_past_time_note_comes_first_and_model_gets_the_target_time(monkeypatch):
    from datetime import datetime
    from zoneinfo import ZoneInfo
    _store()
    seen = []
    _model_says(monkeypatch, "Ngày mai lúc 3 giờ chiều trời mát.", seen)
    tue_2150 = datetime(2026, 10, 27, 21, 50, tzinfo=ZoneInfo("America/Los_Angeles"))
    real_resolve = ask.timeref.resolve
    monkeypatch.setattr(ask.timeref, "resolve", lambda q, now: real_resolve(q, tue_2150))
    r = ask.answer("Hôm nay ở Stockton làm việc ngoài trời lúc 3 giờ chiều có an toàn không?", "vi", "CAZ159")
    assert r["answer"].startswith("3 giờ chiều hôm nay đã qua, đây là dự báo cho 3 giờ chiều ngày mai (thứ Tư).\n")
    user = seen[0]["messages"][1]["content"]
    assert "TIME ASKED ABOUT: Wednesday 3:00 PM" in user and "forecast_at_time_asked" in user


def test_ask_uses_the_standard_model_minimal_effort_and_reports_timings(monkeypatch):
    _store()
    calls = []

    def fake(provider, model, messages, **kw):
        calls.append((model, kw))
        return ChatResult(text="Hot.", model=model, prompt_tokens=1, completion_tokens=1, reasoning_tokens=0,
                          cost_usd=0.0, cache_hit=False, raw={})
    monkeypatch.setattr(ask, "chat", fake)
    monkeypatch.setattr(config, "USE_CONTRIBUTOR", True)  # dev setting must not leak into user questions
    r = ask.answer("Is it hot?", "en", "CAZ159")
    model, kw = calls[0]
    assert model == "muse-spark-1.3" and kw["reasoning_effort"] == "minimal" and kw["max_tokens"] == ask.MAX_ANSWER_TOKENS[ask.ASK_REASONING_EFFORT]
    assert set(r["timings_ms"]) == {"data", "context", "model", "check", "total"}


def test_on_demand_snapshots_are_reused_for_a_while(monkeypatch):
    built = []
    snap = scenarios.build("heatwave", "CAZ159")
    monkeypatch.setattr(ask, "_on_demand", {})
    monkeypatch.setattr(ask.nws, "get_zone_alerts", lambda rec: [])
    monkeypatch.setattr(ask.snapshot, "build_snapshot", lambda rec, alerts, prev=None: built.append(1) or snap)
    assert ask.zone_snapshot("CAZ159") is snap and ask.zone_snapshot("CAZ159") is snap and built == [1]


def test_time_range_gets_a_summary_over_the_whole_range(monkeypatch):
    # Seen live: asked about 6 AM-2 PM tomorrow, the answer gave only 6 AM and "I don't know".
    snap = _store()
    seen = []
    _model_says(monkeypatch, "Sáng thứ năm mát, trưa nóng.", seen)
    first = datetime.fromisoformat(snap["forecast"]["hours"][0]["time"])
    start = (first + timedelta(days=1)).replace(hour=6)
    ref = timeref.TimeRef(target=start, passed=False, end=start.replace(hour=14))
    ctx = ask.build_context(snap, [], ref)
    rng = ctx["time_range_asked"]
    temps = [h["temp_f"] for h in snap["forecast"]["hours"]
             if start - timedelta(hours=1) < datetime.fromisoformat(h["time"]) <= start.replace(hour=14)]
    assert rng["temp_at_start_f"] == temps[0] and rng["temp_at_end_f"] == temps[-1] and rng["warmest_f"] == max(temps)
    assert len(rng["hourly"]) == len(temps) and len(ctx["forecast_hourly_48h"]) == len(snap["forecast"]["hours"])
    assert ctx["days"] and "forecast_at_time_asked" not in ctx
    # the whole answer path: Vietnamese weekday names are capitalized in code
    r = ask.answer("Ngày mai từ sáu giờ sáng đến hai giờ chiều tôi nên chuẩn bị gì?", "vi", "CAZ159")
    assert "thứ Năm" in r["answer"] and r["data_time"] == snap["generated_at"]
    assert "time_range_asked" in seen[0]["messages"][1]["content"]


def test_vietnamese_answer_style_fixed_in_code(monkeypatch):
    # Reviewer (2026-10-28): advice starts with "Hãy", °F with °C, weekday names capitalized.
    _store()
    _model_says(monkeypatch, "Sáng thứ năm trời mát 51°F. Bạn nên mặc nhiều lớp áo. Bạn có thể nghỉ trưa.")
    r = ask.answer("Sáng mai thời tiết thế nào?", "vi", "CAZ159")
    assert r["answer"] == "Sáng thứ Năm trời mát 51°F (11°C). Hãy mặc nhiều lớp áo. Bạn có thể nghỉ trưa."
    assert r["data_time_text"].endswith(("thứ Hai", "thứ Ba", "thứ Tư", "thứ Năm", "thứ Sáu", "thứ Bảy", "Chủ Nhật"))
    _model_says(monkeypatch, "Yes. It will reach 69°F.")
    assert ask.answer("Is it hot today?", "en", "CAZ159")["answer"] == "Yes. It will reach 69°F."


def test_place_questions_use_a_cited_web_search(monkeypatch):
    _store()
    found = {"answer": "Trung tâm làm mát chính thức của quận (cập nhật 2021):\nBoggs Tract Community Center: 533 S. Los "
                       "Angeles St, M-F 8am-5pm", "sources": [{"title": "Regular Cooling Locations",
                       "url": "https://sjready.org/x.pdf", "source": "sjready.org"}], "searches": 2, "cost_usd": 0.018}
    monkeypatch.setattr(ask.places, "find", lambda question, lang, snap: dict(found))
    r = ask.answer("Ở đâu có trung tâm làm mát?", "vi", "CAZ159")
    assert r["kind"] == "places" and r["answer"].endswith(ask.places.CHECK_FIRST["vi"])
    assert r["sources"][0]["source"] == "sjready.org"
    # medical wording in a search answer: the fixed 211 sentence instead
    monkeypatch.setattr(ask.places, "find", lambda question, lang, snap: {**found, "answer": "Take ibuprofen there."})
    assert ask.answer("Where is a cooling center?", "en", "CAZ159")["answer"] == ask.HELP_211["en"]


def test_search_answer_parsing_keeps_only_the_final_cited_message():
    output = [{"type": "message", "content": [{"text": "I'll search now.", "annotations": []}]},
              {"type": "web_search_call", "status": "completed"},
              {"type": "message", "content": [{"text": "**Library**: 1 Main St", "annotations": [
                  {"type": "url_citation", "url": "https://www.stocktonca.gov/a", "title": "City"},
                  {"type": "url_citation", "url": "https://www.stocktonca.gov/a", "title": "City"}]}]}]
    text, cites = ask.places._final_message(output)
    assert text == "**Library**: 1 Main St" and len(cites) == 2
    assert ask.places.sources(cites) == [{"title": "City", "url": "https://www.stocktonca.gov/a", "source": "stocktonca.gov"}]


# --- place questions: the trigger, the retry and the fallback links (2026-10-28 live failure) ---

REAL_FIND = ask.places.find  # the autouse fixture stubs places.find (no web search offline)

PLACE_QUESTIONS = [
    "Where is the cooling center near me?", "Where is the nearest cooling centre?", "Any warming centers open tonight?",
    "Is there an emergency shelter nearby?", "Where can I go to cool off?", "Where should my family go if it floods?",
    "where can we stay tonight", "I need somewhere cool to rest", "Is there a place to sleep tonight?",
    "Is the library open as a cooling station?", "Where can my kids go to get out of the heat?",
    "¿Dónde está el centro de enfriamiento?", "¿Hay un refugio cerca?", "¿Dónde puedo ir a refrescarme?",
    "¿Adónde podemos ir esta noche?", "Necesito un lugar fresco para descansar",
    "Trung tâm làm mát gần tôi ở đâu?", "Gần đây có chỗ nào mát để nghỉ không?", "Tôi cần nơi trú ẩn tối nay",
    "Có nơi nào có máy lạnh không?", "附近哪里有避暑中心？", "근처에 무더위 쉼터가 어디 있나요?",
    "Saan may cooling center?", "أين أقرب مركز تبريد؟",
]
NOT_PLACE_QUESTIONS = [
    "Is it hot today?", "Will it rain on Friday?", "Do I need to repair anything for tomorrow?",
    "Is it safe to work outside this afternoon?", "What should I wear tomorrow?", "Will it be cool tonight?",
    "Will it go below freezing?", "Where does the wind come from?", "Chất lượng không khí ngày mai thế nào?",
    "¿Hace calor hoy?", "明天热吗？",
]


@pytest.mark.parametrize("question", PLACE_QUESTIONS)
def test_place_trigger_wording(question):
    assert ask.PLACE_QUESTION.search(question), question


@pytest.mark.parametrize("question", NOT_PLACE_QUESTIONS)
def test_place_trigger_leaves_weather_questions_alone(question):
    assert not ask.PLACE_QUESTION.search(question), question


@pytest.mark.parametrize("scenario", ["calm", "heatwave", "smoke"])
def test_place_question_always_searches_whatever_the_weather(monkeypatch, scenario):
    # a mild day used to look like "no need for a cool place": the search must run anyway, no chat model call
    _store(scenario)
    calls = []
    monkeypatch.setattr(ask.places, "find", lambda q, lang, snap: calls.append(q) or {"failed": "no_citation"})
    monkeypatch.setattr(ask, "chat", lambda *a, **kw: pytest.fail("a place question must not reach the chat model"))
    r = ask.answer("Where is the cooling center near me?", "en", "CAZ159")
    assert calls == ["Where is the cooling center near me?"] and r["kind"] == "answer"


def test_failed_search_gives_the_211_sentence_with_tappable_links(monkeypatch):
    _store()
    monkeypatch.setattr(ask.places, "find", lambda q, lang, snap: {"failed": "incomplete", "cost_usd": 0.03})
    r = ask.answer("Where is the cooling center near me?", "en", "CAZ159")
    assert r["answer"] == ask.HELP_211["en"] and r["reason"] == "no_cited_places:incomplete"
    assert [(l["kind"], l["url"]) for l in r["links"]] == [
        ("tel", "tel:211"), ("web", "https://www.211.org/"), ("web", "https://www.sjgov.org/")]
    assert r["links"][0]["label"] == "Call 211" and "San Joaquin County" in r["links"][2]["label"]
    es = ask.answer("¿Dónde hay un refugio?", "es", "CAZ159")["links"]
    assert es[0]["label"] == "Llamar al 211" and es[2]["label"] == "Sitio web de San Joaquin County"
    # a county we have no site for: USA.gov's directory of local governments, never a guessed URL
    monkeypatch.setattr(ask.zones, "get", lambda z: {"county": "TXC453", "tz": "America/Chicago"})
    assert ask.answer("Where is a shelter?", "en", "CAZ159")["links"][2]["url"] == places_directory()
    # over the daily budget: no search, but the sentence and links still help
    monkeypatch.setattr(ask.budget, "over_budget", lambda: True)
    over = ask.answer("Where is a shelter?", "en", "CAZ159")
    assert over["answer"] == ask.HELP_211["en"] and over["links"] and over["reason"] == "budget"


def places_directory():
    return ask.places.GOVERNMENT_DIRECTORY


def _search_result(ok, reason="incomplete", searches=2):
    if ok:
        return {"ok": True, "answer": "Library: 1 Main St", "sources": [{"title": "t", "url": "u", "source": "s"}],
                "searches": searches, "cost_usd": 0.02}
    return {"ok": False, "reason": reason, "searches": searches, "cost_usd": 0.03}


def test_search_retries_once_with_a_stricter_attempt(monkeypatch):
    seen = []
    results = iter([_search_result(False, "incomplete", 10), _search_result(True, searches=2)])
    monkeypatch.setattr(ask.places, "_search_once",
                        lambda q, lang, snap, attempt, deadline: seen.append((attempt["searches"], deadline)) or next(results))
    found = REAL_FIND("q", "en", {"place": "Stockton, CA"})
    assert found["answer"] and found["attempts"] == 2 and found["searches"] == 12
    assert seen[0] == (3, ask.places.FIRST_DEADLINE_S) and seen[1][0] == 2
    assert ask.places.MIN_RETRY_S <= seen[1][1] <= ask.places.TOTAL_BUDGET_S  # the retry gets what is left
    assert ask.places.TOTAL_BUDGET_S < 28  # inside Ask's Lambda timeout and API Gateway's 30 s


def test_search_stops_when_no_time_is_left_for_a_retry(monkeypatch):
    clock = iter([0.0, 20.0, 20.0])  # the first try used 20 s of the 22: not enough for a retry
    monkeypatch.setattr(ask.places.time, "monotonic", lambda: next(clock))
    calls = []
    monkeypatch.setattr(ask.places, "_search_once", lambda *a: calls.append(1) or _search_result(False, "timeout", 0))
    found = REAL_FIND("q", "en", {})
    assert len(calls) == 1 and found["failed"] == "timeout" and "answer" not in found


def test_search_that_ran_out_of_tokens_or_has_no_citation_is_not_used(monkeypatch):
    class _Responses:
        def __init__(self, raw):
            self.raw = raw

        def create(self, **params):
            return type("R", (), {"model_dump": lambda s: self.raw})()

    def run(raw):
        client = type("C", (), {"responses": _Responses(raw)})()
        monkeypatch.setattr(ask.places.llm, "_client", lambda provider: client)
        return ask.places._search_once("q", "en", {"place": "Stockton, CA"}, ask.places.ATTEMPTS[0], 5)

    note = {"type": "message", "content": [{"text": "I'll open the county page.", "annotations": []}]}
    usage = {"input_tokens": 100, "output_tokens": 1500}
    # the live failure: status incomplete (max_output_tokens), the last message a progress note
    assert run({"status": "incomplete", "incomplete_details": {"reason": "max_output_tokens"},
                "output": [note], "usage": usage})["reason"] == "incomplete"
    assert run({"status": "completed", "output": [note], "usage": usage})["reason"] == "no_citation"
    cited = {"type": "message", "content": [{"text": "Library: 1 Main St", "annotations": [
        {"type": "url_citation", "url": "https://www.stocktonca.gov/a", "title": "City"}]}]}
    assert run({"status": "completed", "output": [cited], "usage": usage})["ok"]

    def slow(fn, seconds):
        raise ask.places.llm.CallTimeout()
    monkeypatch.setattr(ask.places.llm, "_with_deadline", slow)
    assert ask.places._search_once("q", "en", {}, ask.places.ATTEMPTS[0], 1)["reason"] == "timeout"
