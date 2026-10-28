"""Offline tests: clock times in questions, resolved in code against the zone's local time."""
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest

from climateguard import timeref

LA = ZoneInfo("America/Los_Angeles")
TUE_2150 = datetime(2026, 10, 27, 21, 50, tzinfo=LA)  # Tuesday 9:50 PM (the live test)
TUE_0900 = datetime(2026, 10, 27, 9, 0, tzinfo=LA)


# --- the four required cases ---

def test_past_time_today_answers_for_tomorrow_and_says_so():
    q = "Hôm nay ở Stockton làm việc ngoài trời lúc 3 giờ chiều có an toàn không?"
    ref = timeref.resolve(q, TUE_2150)
    assert ref.passed and ref.target == datetime(2026, 10, 28, 15, 0, tzinfo=LA)
    assert timeref.note(ref, "vi") == "3 giờ chiều hôm nay đã qua, đây là dự báo cho 3 giờ chiều ngày mai (thứ Tư)."
    assert "Wednesday" in ref.prompt_line() and "already passed" in ref.prompt_line()


def test_future_time_today_is_today_with_no_note():
    ref = timeref.resolve("Is it safe to work outside at 3 PM?", TUE_0900)
    assert not ref.passed and ref.target == datetime(2026, 10, 27, 15, 0, tzinfo=LA)
    assert timeref.note(ref, "en") is None


@pytest.mark.parametrize("q", ["Will it be hot at 3 PM tomorrow?", "Ngày mai lúc 3 giờ chiều có nóng không?",
                               "¿Hará calor mañana a las 3 de la tarde?", "明天下午3点热吗？", "내일 오후 3시에 더울까요?"])
def test_tomorrow_stated_explicitly_is_tomorrow_with_no_note(q):
    ref = timeref.resolve(q, TUE_2150)
    assert not ref.passed and ref.target == datetime(2026, 10, 28, 15, 0, tzinfo=LA)
    assert timeref.note(ref, "en") is None


@pytest.mark.parametrize("q", ["Is it safe to work outside today?", "Hôm nay có nắng nóng không?",
                               "Will the AQI go above 150?", "Is 95 degrees dangerous?",
                               "Can I work 3 hours in this heat?", "3시간 일해도 되나요?", "هل أعمل 3 مرات؟",
                               "Will it be hot on Friday at 3 PM?"])
def test_no_clock_time_or_another_day_gives_no_timeref(q):
    assert timeref.resolve(q, TUE_2150) is None


# --- parsing in all 7 languages ---

@pytest.mark.parametrize("q,hour,minute", [
    ("at 3pm", 15, 0), ("at 3:30 p.m.", 15, 30), ("around 15:00", 15, 0), ("at 7 am", 7, 0),
    ("a las 3 de la tarde", 15, 0), ("a las 8 de la noche", 20, 0), ("a las 6 de la mañana", 6, 0),
    ("lúc 3 giờ chiều", 15, 0), ("lúc 3 giờ 30 chiều", 15, 30), ("lúc 11 giờ trưa", 11, 0), ("lúc 1 giờ trưa", 13, 0),
    ("lúc 7 giờ sáng", 7, 0), ("lúc 8 giờ tối", 20, 0), ("lúc 3h chiều", 15, 0),
    ("下午3点", 15, 0), ("下午3点半", 15, 30), ("上午10点", 10, 0),
    ("오후 3시", 15, 0), ("오후 3시 반", 15, 30), ("오전 9시", 9, 0),
    ("alas-3 ng hapon", 15, 0), ("alas 7 ng umaga", 7, 0),
    ("الساعة 3 مساءً", 15, 0), ("الساعة ٣ مساءً", 15, 0), ("الساعة 8 صباحًا", 8, 0),
    ("at 3", 15, 0),  # no AM/PM word: 1-6 is afternoon for an outdoor-work question
])
def test_clock_times_in_every_language(q, hour, minute):
    ref = timeref.resolve(q, TUE_0900.replace(hour=0, minute=30))  # just after midnight: all still ahead today
    assert (ref.target.hour, ref.target.minute) == (hour, minute)


# --- the note, in every language ---

@pytest.mark.parametrize("lang,expected", [
    ("en", "3 PM today has already passed. This is the forecast for 3 PM tomorrow (Wednesday)."),
    ("es", "Las 3 de la tarde de hoy ya pasaron. Este es el pronóstico para mañana (miércoles) a las 3 de la tarde."),
    ("vi", "3 giờ chiều hôm nay đã qua, đây là dự báo cho 3 giờ chiều ngày mai (thứ Tư)."),
    ("zh", "今天下午3点已经过了，以下是明天（星期三）下午3点的预报。"),
    ("tl", "Lumipas na ang alas-3 ng hapon ngayong araw. Ito ang forecast para sa alas-3 ng hapon bukas (Miyerkoles)."),
    ("ko", "오늘 오후 3시는 이미 지났습니다. 내일(수요일) 오후 3시 예보입니다."),
    ("ar", "لقد مضت الساعة 3 مساءً اليوم. هذه توقعات الساعة 3 مساءً غدًا (الأربعاء)."),
])
def test_note_in_every_language(lang, expected):
    ref = timeref.resolve("at 3 PM", TUE_2150)
    assert timeref.note(ref, lang) == expected


def test_spanish_one_oclock_is_singular():
    ref = timeref.resolve("a la 1 de la tarde", TUE_2150)
    assert timeref.note(ref, "es").startswith("La 1 de la tarde de hoy ya pasó.")


@pytest.mark.parametrize("q,expect", [
    ("Hôm nay (thứ Ba) lúc 3 giờ chiều có nóng không?", "passed"),     # today's weekday: still today
    ("Thứ Tư lúc 3 giờ chiều có nóng không?", "tomorrow"),               # tomorrow's weekday
    ("Thứ Sáu lúc 3 giờ chiều có nóng không?", None),                    # another day: left to the model
    ("Will it be hot this weekend at 3 PM?", None),
])
def test_weekday_names(q, expect):
    ref = timeref.resolve(q, TUE_2150)
    got = None if ref is None else "passed" if ref.passed else "tomorrow"
    assert got == expect


# --- ranges and number words (from the iPhone test, 2026-10-28) ---

WED_1205 = datetime(2026, 10, 28, 12, 5, tzinfo=LA)


def test_range_with_vietnamese_number_words():
    q = "Ngày mai tôi làm ngoài đồng từ sáu giờ sáng đến hai giờ chiều, tôi nên chuẩn bị gì?"
    ref = timeref.resolve(q, WED_1205)
    assert ref.target == datetime(2026, 10, 29, 6, 0, tzinfo=LA) and ref.end == datetime(2026, 10, 29, 14, 0, tzinfo=LA)
    assert not ref.passed and "Thursday 6:00 AM to Thursday 2:00 PM" in ref.prompt_line()


@pytest.mark.parametrize("q,hour", [
    ("¿Hace calor a las tres de la tarde?", 15), ("a la una de la tarde", 13), ("at six pm", 18),
    ("Lúc ba giờ chiều có nóng không?", 15),
])
def test_number_words_before_a_clock_word(q, hour):
    assert timeref.resolve(q, WED_1205).target.hour == hour


@pytest.mark.parametrize("q", ["Tôi có hai con, hôm nay nóng không?", "¿Hay dos refugios?", "one more question"])
def test_number_words_without_a_clock_word_are_not_times(q):
    assert timeref.resolve(q, WED_1205) is None


def test_range_already_over_today_moves_to_tomorrow_with_a_range_note():
    ref = timeref.resolve("từ 6 giờ sáng đến 10 giờ sáng", WED_1205)
    assert ref.passed and ref.end.day == 29
    assert timeref.note(ref, "vi") == ("6 giờ sáng–10 giờ sáng hôm nay đã qua, đây là dự báo cho "
                                       "6 giờ sáng–10 giờ sáng ngày mai (thứ Năm).")
