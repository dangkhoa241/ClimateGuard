"""Offline tests: °F/°C formatting in code, and the "warning ending with no hazard left" guardrail."""
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]

import pytest

from climateguard import alerts_store, config, monitor, notify, replays, scenarios as sc, units, zones


@pytest.fixture(autouse=True)
def local(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "LOCAL_DIR", tmp_path)
    monkeypatch.setattr(config, "STORAGE", "local")
    monkeypatch.setattr(config, "NOTIFY_MODE", "dryrun")


# --- temperatures ---

@pytest.mark.parametrize("lang,text,expected", [
    ("en", "up to 114F today", "up to 114°F today"),
    ("en", "up to 114 °F", "up to 114°F"),
    ("vi", "lên đến 114F.", "lên đến 114°F (46°C)."),
    ("vi", "lên đến 114 độ F, rất nóng", "lên đến 114°F (46°C), rất nóng"),
    ("es", "hasta 95 grados F", "hasta 95°F (35°C)"),
    ("vi", "lạnh -5F", "lạnh -5°F (-21°C)"),
    ("vi", "đeo khẩu trang N95", "đeo khẩu trang N95"),
    ("es", "a las 5 PM", "a las 5 PM"),
])
def test_temperature_formatting(lang, text, expected):
    assert units.format_temps(text, lang) == expected
    assert units.format_temps(expected, lang) == expected  # idempotent


def test_send_alert_stores_both_units_for_non_english():
    run = monitor.Run(zone="CAZ159", snapshot=sc.build("heatwave"), namespace="EVAL-units")
    r = monitor.tool_send_alert(run, {"zone": "CAZ159", "hazard": "heat", "severity": "extreme", "reason": "r",
                                      "messages_by_language": {"en": "Highs up to 108F today.",
                                                               "es": "Máxima de 108F hoy.",
                                                               "vi": "Hôm nay (thứ Ba), nhiệt độ lên đến 108F."}})
    assert r["sent"]
    [row] = alerts_store.recent_sent("EVAL-units")
    assert row["messages"]["en"] == "Highs up to 108°F today."
    assert "108°F (42°C)" in row["messages"]["es"] and "108°F (42°C)" in row["messages"]["vi"]


def test_translated_alerts_get_both_units(monkeypatch):
    monkeypatch.setattr(notify, "translate_alert", lambda text, lang: ("最高 108F。", True))
    zone = dict(zones.DEMO_ZONES["CAZ159"], langs=["zh"])
    notify.deliver(zone, "heat", "extreme", {"en": "Highs 108F.", "es": "x", "vi": "y"})
    outbox = (config.LOCAL_DIR / "outbox.jsonl").read_text(encoding="utf-8")
    assert "108°F (42°C)" in outbox


# --- warning ending with no hazard left ---

def _snap(temp_peak, rh, hours_left, event="Extreme Heat Warning", aqi_now=45):
    def parts(tz):
        curve = sc.heat_curve(temp_peak) if temp_peak >= 90 else (lambda h: temp_peak)
        return {"hours": sc.hours(tz, curve, lambda h: rh), "aqi": sc.aqi(tz, aqi_now, [aqi_now, aqi_now]),
                "alerts": [sc.nws_alert(tz, event, "Severe", hours_left, event, "d", "i")]}
    return sc.assemble("CAZ159", parts(ZoneInfo("America/Los_Angeles")), "t")


def _try(snap, hazard="heat"):
    run = monitor.Run(zone="CAZ159", snapshot=snap, namespace="EVAL-g")
    return monitor.validate_alert(run, {"zone": "CAZ159", "hazard": hazard, "severity": "extreme", "reason": "r",
                                        "messages_by_language": {"en": "Heat.", "es": "Calor.",
                                                                 "vi": "Nắng nóng."}})


def test_warning_ending_with_mild_weather_is_rejected():
    reason = _try(_snap(76, 40, hours_left=2))
    assert reason and "danger is over" in reason and "76°F" in reason


def test_warning_ending_but_heat_returns_is_allowed():
    assert _try(_snap(104, 20, hours_left=2)) is None


def test_long_warning_with_mild_data_is_allowed():
    # "trust the official warning" case: plenty of time left, so the data mismatch doesn't block it
    assert _try(_snap(82, 40, hours_left=30)) is None


def test_air_alert_ending_with_clean_air_is_rejected_but_dirty_air_is_not():
    assert "danger is over" in _try(_snap(80, 35, 1, event="Air Quality Alert", aqi_now=42), hazard="smoke")
    assert _try(_snap(80, 35, 1, event="Air Quality Alert", aqi_now=160), hazard="smoke") is None


def test_hours_left_uses_the_replay_time():
    snap = replays.snapshot_for("heat_2022", "record_day_morning")  # Sept 6 2022, 07:00; warning ends Sept 9 20:00
    run = monitor.Run(zone="CAZ159", snapshot=snap)
    assert run.now == datetime.fromisoformat("2022-09-06T07:00:00-07:00")
    assert run.hours_left(snap["alerts"][0]) == 85.0


# --- Vietnamese review round 2: masks, watch + warning, feels-like, flood wording, casing ---

from climateguard import guardrails, translate  # noqa: E402

MASK_IN_EVERY_LANGUAGE = {
    "en": "If you must go outside, wear an N95 mask.", "es": "Si sale, use una mascarilla N95.",
    "vi": "Nếu phải ra ngoài, hãy đeo khẩu trang vừa khít.", "zh": "外出时请佩戴口罩。",
    "tl": "Kung lalabas, magsuot ng maskara.", "ko": "외출 시 마스크를 착용하세요.", "ar": "ارتدِ كمامة عند الخروج.",
}
NO_MASK = {"en": "Limit time outdoors.", "es": "Limite el tiempo afuera.", "vi": "Hãy hạn chế ra ngoài.",
           "zh": "减少户外活动。", "tl": "Limitahan ang oras sa labas.", "ko": "야외 활동을 줄이세요.",
           "ar": "قلل الوقت في الخارج."}


@pytest.mark.parametrize("lang", list(MASK_IN_EVERY_LANGUAGE))
def test_mask_detected_in_every_language(lang):
    assert guardrails.mentions_mask(MASK_IN_EVERY_LANGUAGE[lang])
    assert not guardrails.mentions_mask(NO_MASK[lang])


def _air(pollutant, aqi_fc, alert_text=None):
    def parts(tz):
        alerts = [sc.nws_alert(tz, "Air Quality Alert", "Unknown", 24, alert_text, alert_text, "i")] if alert_text else []
        return {"hours": sc.hours(tz, sc.heat_curve(95), lambda h: 20), "alerts": alerts,
                "aqi": sc.aqi(tz, 90, [aqi_fc, 90], pollutant=pollutant)}
    return sc.assemble("CAZ159", parts(ZoneInfo("America/Los_Angeles")), "air")


def test_particle_pollution_only_for_particles():
    assert not guardrails.particle_pollution(_air("O3", 185))
    assert not guardrails.particle_pollution(_air("O3", 185, "Air Quality Alert for ozone"))
    assert not guardrails.particle_pollution(replays.snapshot_for("heat_2022", "record_day_morning"))  # ozone 208
    assert guardrails.particle_pollution(_air("PM2.5", 160))
    assert guardrails.particle_pollution(_air("O3", 120, "Air Quality Alert for wildfire smoke"))
    assert guardrails.particle_pollution(replays.snapshot_for("smoke_2020", "peak"))


def test_masks_still_allowed_when_ozone_is_worse_than_the_smoke():
    from eval_cases import _ozone_and_smoke
    tz = ZoneInfo("America/Los_Angeles")
    both = sc.assemble("CAZ159", {"hours": sc.hours(tz, sc.heat_curve(97), lambda h: 20), "alerts": [],
                                  "aqi": _ozone_and_smoke(tz)}, "both")
    assert both["aqi"]["current"]["pollutant"] == "O3"  # ozone is the headline pollutant...
    assert guardrails.particle_pollution(both)  # ...but the smoke is still there
    # smoke only in the forecast, ozone worst that day (AirNow keeps the worst pollutant per day)
    fc_only = _air("O3", 185)
    fc_only["aqi"]["forecast"][0]["particles_unhealthy"] = True
    assert guardrails.particle_pollution(fc_only)
    run = monitor.Run(zone="CAZ159", snapshot=both, namespace="EVAL-both")
    msgs = {lang: f"Air is unhealthy. {MASK_IN_EVERY_LANGUAGE[lang]}" for lang in ("en", "es", "vi")}
    msgs["es"] = "El aire es dañino. Si sale, use una mascarilla N95."
    assert monitor.validate_alert(run, {"zone": "CAZ159", "hazard": "smoke", "severity": "high", "reason": "r",
                                        "messages_by_language": msgs}) is None


@pytest.mark.parametrize("lang", ["en", "es", "vi"])
def test_mask_rejected_for_ozone_in_each_reviewed_language(lang):
    ok = {"en": "Ozone is high today. Limit time outdoors.", "es": "Ozono alto hoy. Limite el tiempo afuera.",
          "vi": "Hôm nay khí ôzôn tăng cao. Hãy hạn chế ra ngoài."}
    run = monitor.Run(zone="CAZ159", snapshot=_air("O3", 185), namespace="EVAL-mask")
    args = {"zone": "CAZ159", "hazard": "smoke", "severity": "high", "reason": "r"}
    assert monitor.validate_alert(run, {**args, "messages_by_language": ok}) is None
    bad = {**ok, lang: ok[lang] + " " + MASK_IN_EVERY_LANGUAGE[lang]}
    reason = monitor.validate_alert(run, {**args, "messages_by_language": bad})
    assert "Masks do not protect against ozone" in reason
    from run_eval import rejection_kind
    assert rejection_kind(reason) == "mask_without_particles"
    smoke = monitor.Run(zone="CAZ159", snapshot=_air("PM2.5", 185), namespace="EVAL-mask2")
    assert monitor.validate_alert(smoke, {**args, "messages_by_language": bad}) is None


@pytest.mark.parametrize("lang", ["zh", "tl", "ko", "ar"])
def test_translation_that_adds_a_mask_falls_back_to_english(monkeypatch, lang):
    from climateguard.llm import ChatResult
    monkeypatch.setattr(translate, "chat", lambda *a, **k: ChatResult(
        text=MASK_IN_EVERY_LANGUAGE[lang], model="m", prompt_tokens=1, completion_tokens=1, reasoning_tokens=0, cost_usd=0.0,
        cache_hit=False, raw={}))
    assert translate.translate_alert("Limit time outdoors.", lang) == ("Limit time outdoors.", False)
    # a mask that IS in the English (smoke) may be translated
    assert translate.translate_alert("Wear an N95 mask outside.", lang) == (MASK_IN_EVERY_LANGUAGE[lang], True)


def test_watch_not_mentioned_next_to_a_warning():
    snap = replays.snapshot_for("flood_2023", "warning_night")
    run = monitor.Run(zone=snap["zone"], snapshot=snap, namespace="EVAL-watch")
    vi = "Cảnh báo lũ lụt có hiệu lực. Tuyệt đối không đi bộ hoặc lái xe qua vùng nước ngập."
    args = {"zone": snap["zone"], "hazard": "flood", "severity": "high", "reason": "r"}
    both = {"en": "Flood Warning until 9:30 AM Wednesday and Flood Watch through Wednesday.",
            "es": "Aviso de inundación hasta el miércoles. Nunca camine ni maneje por agua de inundación.",
            "vi": vi}
    from run_eval import rejection_kind
    assert rejection_kind(monitor.validate_alert(run, {**args, "messages_by_language": both})) == "watch_with_warning"
    only_warning = {**both, "en": "Flood Warning until 9:30 AM Wednesday. Never drive through floodwater."}
    assert monitor.validate_alert(run, {**args, "messages_by_language": only_warning}) is None
    weak_vi = {**only_warning, "vi": "Cảnh báo lũ lụt có hiệu lực. Hãy tránh đi qua nước lũ."}
    assert rejection_kind(monitor.validate_alert(run, {**args, "messages_by_language": weak_vi})) == "flood_wording"
    weak_es = {**only_warning, "es": "Aviso de inundación hasta el miércoles. Evite el agua de inundación."}
    assert rejection_kind(monitor.validate_alert(run, {**args, "messages_by_language": weak_es})) == "flood_wording"


def test_feels_like_only_when_5F_above_air_temperature():
    msgs = {"en": "Up to 104F, feels like 106F.", "es": "Hasta 104F.", "vi": "Nhiệt độ lên tới 104F."}
    args = {"zone": "CAZ159", "hazard": "heat", "severity": "high", "reason": "r", "messages_by_language": msgs}
    dry = monitor.Run(zone="CAZ159", snapshot=_snap(104, 20, 30), namespace="EVAL-fl")  # heat index ~ air temp
    humid = monitor.Run(zone="CAZ159", snapshot=_snap(100, 55, 30), namespace="EVAL-fl2")
    assert dry.snapshot["summary"]["max_heat_index_f"] - dry.snapshot["summary"]["max_temp_f"] < 5
    assert humid.snapshot["summary"]["max_heat_index_f"] - humid.snapshot["summary"]["max_temp_f"] >= 5
    from run_eval import rejection_kind
    assert rejection_kind(monitor.validate_alert(dry, args)) == "feels_like_too_close"
    assert monitor.validate_alert(humid, args) is None


@pytest.mark.parametrize("text,expected", [
    ("Cảnh báo khói có hiệu lực Hôm nay (thứ Bảy) và Chủ Nhật.", "Cảnh báo khói có hiệu lực hôm nay (thứ Bảy) và Chủ Nhật."),
    ("Hôm nay (thứ Ba), nắng nóng. Tối nay trời mát.", "Hôm nay (thứ Ba), nắng nóng. Tối nay trời mát."),
    ("Có hiệu lực đến 11 giờ Tối nay (thứ Hai).", "Có hiệu lực đến 11 giờ tối nay (thứ Hai)."),
])
def test_vietnamese_time_words_lowercased_mid_sentence(text, expected):
    assert guardrails.fix_vi_case(text) == expected


# --- reviewer's wording decisions, round 3 (meaning errors found by back-translation) ---

@pytest.mark.parametrize("aqi,phrase,ok", [
    (157, "rất có hại cho sức khỏe", False),   # the run-5 error: Unhealthy written as Very Unhealthy
    (157, "có hại cho sức khỏe", True),
    (208, "rất có hại cho sức khỏe", True),
    (208, "có hại cho sức khỏe", False),
    (148, "có hại cho nhóm nhạy cảm", True),
    (148, "có hại cho sức khỏe", False),
    (320, "nguy hiểm cho sức khỏe", True),
    (320, "rất có hại cho sức khoẻ", False),    # other spelling of khỏe is recognized too
])
def test_vi_aqi_wording_matches_the_aqi_value(aqi, phrase, ok):
    text = f"Hôm nay (thứ Ba), không khí {phrase} (chỉ số AQI lên tới {aqi})."
    assert (guardrails.vi_aqi_wording_issue(text, None) is None) == ok


def test_vi_aqi_wording_two_days_and_fallback():
    two_days = ("Hôm nay (thứ Ba) chỉ số AQI lên tới 185 ở mức có hại cho sức khỏe, ngày mai (thứ Tư) "
                "ở mức có hại cho nhóm nhạy cảm.")
    assert guardrails.vi_aqi_wording_issue(two_days, None) is None
    no_number = "Khói cháy rừng làm không khí rất có hại cho sức khỏe."
    assert guardrails.vi_aqi_wording_issue(no_number, 160) and guardrails.vi_aqi_wording_issue(no_number, 230) is None
    assert guardrails.vi_aqi_wording_issue("Nắng nóng nguy hiểm cho sức khỏe.", 40) is None  # not about air


@pytest.mark.parametrize("text,ok", [
    ("Si trabaja al aire libre, haga el trabajo pesado temprano en la mañana o en la tarde si puede.", False),
    ("Haga las tareas pesadas por la tarde.", False),
    ("Si trabaja al aire libre, haga el trabajo pesado temprano en la mañana o al anochecer.", True),
    ("Calor extremo hoy de 1 de la tarde a 7 de la noche. Tome agua.", True),  # a time, not work advice
])
def test_es_afternoon_work_blocked(text, ok):
    assert (guardrails.es_afternoon_work_issue(text) is None) == ok


@pytest.mark.parametrize("events,text,ok", [
    (["Flood Watch"], "Cảnh báo lũ lụt có hiệu lực đến đêm thứ Ba.", False),
    (["Flood Watch"], "Cảnh giác lũ lụt có hiệu lực đến đêm thứ Ba.", True),
    (["Heat Advisory"], "Cảnh báo nắng nóng có hiệu lực.", False),
    (["Heat Advisory"], "Khuyến cáo nắng nóng có hiệu lực.", True),
    (["Flood Advisory", "Flood Warning"], "Cảnh báo lũ lụt có hiệu lực.", True),
    (["Air Quality Alert"], "Cảnh báo chất lượng không khí có hiệu lực.", True),
    ([], "Cảnh báo khói cháy rừng có hiệu lực.", False),  # no NWS product: claim no level
    ([], "Hôm nay (thứ Bảy), không khí có hại cho sức khỏe.", True),
])
def test_vi_alert_level_names(events, text, ok):
    assert (guardrails.vi_level_issue(text, events) is None) == ok


@pytest.mark.parametrize("events,text,ok", [
    (["Flood Warning"], "Aviso de inundación vigente hasta las 11:15 de la noche.", True),
    (["Flood Warning"], "Advertencia de inundación vigente hasta la noche.", False),  # understates a warning
    (["Flood Watch"], "Vigilancia de inundación hasta la noche del martes.", True),
    (["Flood Watch"], "Aviso de inundación hasta la noche del martes.", False),  # overstates a watch
    (["Heat Advisory"], "Advertencia de calor hoy hasta las 8 de la noche.", True),
    (["Heat Advisory"], "Aviso de calor hoy hasta las 8 de la noche.", False),
    (["Air Quality Alert"], "Aviso de calidad del aire hoy y mañana.", True),
    (["Flood Advisory", "Flood Warning"], "Aviso de inundación vigente.", True),
    ([], "Humo hoy, calidad del aire dañina. Quédese adentro.", True),
    ([], "Aviso de humo hoy. Quédese adentro.", False),  # no NWS product: claim no level
    ([], "Quédese adentro hasta nuevo aviso.", True),     # the everyday phrase, not the product
])
def test_es_alert_level_names(events, text, ok):
    assert (guardrails.es_level_issue(text, events) is None) == ok


def test_vi_time_after_midnight():
    text = "Cảnh báo băng giá có hiệu lực từ 2 giờ sáng nay đến 7 giờ sáng thứ Ba."
    assert guardrails.vi_past_morning_issue(text, hour_now=19)  # evening: "sáng nay" is past
    assert guardrails.vi_past_morning_issue(text, hour_now=1) is None  # 1 AM: this morning is still ahead
    assert guardrails.vi_past_morning_issue("Có hiệu lực từ 2 giờ rạng sáng thứ Hai.", hour_now=19) is None


def test_wording_checks_reach_the_agent_with_known_rejection_kinds():
    from run_eval import rejection_kind
    snap = replays.snapshot_for("flood_2023", "watch")
    run = monitor.Run(zone=snap["zone"], snapshot=snap, namespace="EVAL-lvl")
    msgs = {"en": "Flood Watch through Tuesday night. Never walk or drive through floodwater.",
            "es": "Vigilancia de inundación hasta el martes. Nunca camine ni maneje por agua de inundación.",
            "vi": "Cảnh báo lũ lụt có hiệu lực đến đêm thứ Ba. Tuyệt đối không đi bộ hoặc lái xe qua vùng nước ngập."}
    args = {"zone": snap["zone"], "hazard": "flood", "severity": "moderate", "reason": "r"}
    assert rejection_kind(monitor.validate_alert(run, {**args, "messages_by_language": msgs})) == "vi_alert_level"
    fixed = {**msgs, "vi": msgs["vi"].replace("Cảnh báo", "Cảnh giác")}
    assert monitor.validate_alert(run, {**args, "messages_by_language": fixed}) is None
    for reason, kind in ((guardrails.vi_aqi_wording_issue("không khí rất có hại cho sức khỏe (AQI 160)", None), "vi_aqi_wording"),
                         (guardrails.es_afternoon_work_issue("Trabaje en la tarde."), "es_afternoon_work"),
                         (guardrails.vi_past_morning_issue("2 giờ sáng nay", 20), "vi_time_after_midnight")):
        assert rejection_kind(reason) == kind
