"""Clock times in a question ("3 giờ chiều", "3 PM", "a las 3 de la tarde", "下午3点"...), resolved in code
against the zone's local time, so the model never has to decide whether a time has already passed.

  resolve("... lúc 3 giờ chiều ...", now=Tue 21:50)  -> TimeRef(target=Wed 15:00, passed=True)
  passed=True: the person asked about a time earlier today; the answer is for the same time tomorrow,
  and note(lang) says so in their language, as the first sentence of the answer.
A range ("từ 6 giờ sáng đến 2 giờ chiều", "from 6 AM to 2 PM") gives a TimeRef with an end, and Ask
summarizes the forecast over the whole range. Number words are read before a clock word in Vietnamese,
Spanish and English ("sáu giờ sáng", "a las seis", "six o'clock"); other languages need digits.
A question without a clock time gets no TimeRef. Other weekdays ("on Friday") are left to the model.
"""
import re
from dataclasses import dataclass
from datetime import datetime, timedelta

PM_WORDS = r"p\.?\s?m\.?|chiều|tối|tarde|noche|hapon|gabi|下午|晚上|傍晚|오후|저녁|밤|مساء|مساءً|م|عصرا|عصرًا"
AM_WORDS = r"a\.?\s?m\.?|sáng|mañana|madrugada|umaga|上午|早上|凌晨|오전|아침|صباحا|صباحًا|ص"
NOON_WORDS = r"trưa|tanghali|中午|ظهرا|ظهرًا"
NIGHT_WORDS = r"đêm"  # "11 giờ đêm" = 23:00, "1 giờ đêm" = 01:00

# A number counts as a clock time only with a clock word around it (prefix, separator or AM/PM word):
# "AQI 150", "95 degrees", "3 hours", "3시간" (3 hours) and "3 مرات" (3 times) are not times.
_TIME = re.compile(
    r"(?P<pre>上午|早上|凌晨|中午|下午|晚上|傍晚|오전|오후|아침|저녁|밤)?\s*"
    r"(?P<at>\b(?:a las|las|la|at|lúc|vào lúc)\s+|\balas[-\s]?|الساعة\s*)?"
    r"(?<!\d)(?P<h>\d{1,2})(?!\d)"
    r"(?:(?P<sep>\s*(?:giờ|点|點|时|時|시(?!간)|o'?clock)|[:.](?=[0-5]\d)|h(?![a-zA-Z]))"
    r"\s*(?P<m>[0-5]\d|半|반)?\s*(?:phút|分|분)?)?"
    r"(?:\s*(?:de la|ng|del)?\s*(?P<post>" + "|".join((PM_WORDS, AM_WORDS, NOON_WORDS, NIGHT_WORDS)) + r")(?!\w))?",
    re.IGNORECASE)

TOMORROW = re.compile(r"tomorrow|\bmai\b|(?<!de la )(?<!por la )(?<!en la )\bmañana\b|bukas|明天|明日|내일|غدا|غدًا|بكرة",
                      re.IGNORECASE)
# a weekend or date: leave the day to the model (weekday names are checked in _named_day)
OTHER_DAY = re.compile(r"weekend|fin de semana|cuối tuần|周末|週末|주말|katapusan ng linggo|عطلة|周[一二三四五六日]|"
                       r"\d{1,2}/\d{1,2}", re.IGNORECASE)


# Number words -> digits, only right before a clock word, so "hai" (two) or "una" elsewhere stay as they are.
_VI_NUM = {"mười một": 11, "mười hai": 12, "một": 1, "hai": 2, "ba": 3, "bốn": 4, "tư": 4, "năm": 5, "sáu": 6,
           "bảy": 7, "tám": 8, "chín": 9, "mười": 10}
_ES_NUM = {"una": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6, "siete": 7, "ocho": 8, "nueve": 9,
           "diez": 10, "once": 11, "doce": 12}
_EN_NUM = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
           "ten": 10, "eleven": 11, "twelve": 12}
_NUM_WORDS = [
    (re.compile(r"(?<!\w)(" + "|".join(_VI_NUM) + r")(?=\s+giờ)", re.IGNORECASE), _VI_NUM),
    (re.compile(r"(?<=\blas )(" + "|".join(_ES_NUM) + r")\b|(?<=\bla )(una)\b", re.IGNORECASE), _ES_NUM),
    (re.compile(r"\b(" + "|".join(_EN_NUM) + r")(?=\s*(?:o'?clock|a\.?\s?m\b|p\.?\s?m\b))", re.IGNORECASE), _EN_NUM),
]


def _with_digits(question: str) -> str:
    for rx, words in _NUM_WORDS:
        question = rx.sub(lambda m: str(words[(m.group(1) or m.group(2)).lower()]), question)
    return question


@dataclass
class TimeRef:
    target: datetime               # local time the answer is for (the start of a range)
    passed: bool                   # asked about a time already past today -> answering for tomorrow
    end: datetime | None = None    # end of a range ("from 6 AM to 2 PM")

    def prompt_line(self) -> str:
        why = " (the time asked about has already passed today, so answer for tomorrow)" if self.passed else ""
        fmt = lambda t: t.strftime('%A %I:%M %p').replace(' 0', ' ')  # noqa: E731
        span = f"{fmt(self.target)} to {fmt(self.end)}" if self.end else fmt(self.target)
        return f"TIME ASKED ABOUT: {span} local time{why}."


def _hour24(h: int, word: str | None, pre: str | None) -> int | None:
    w = (word or pre or "").lower()
    if h > 24:
        return None
    if h >= 13 or h == 0:
        return h % 24
    if re.fullmatch(PM_WORDS, w, re.IGNORECASE):
        return h if h == 12 else h + 12
    if re.fullmatch(AM_WORDS, w, re.IGNORECASE):
        return 0 if h == 12 else h
    if re.fullmatch(NOON_WORDS, w, re.IGNORECASE):
        return h if h >= 11 else h + 12  # "11 giờ trưa" = 11:00, "1 giờ trưa" = 13:00
    if re.fullmatch(NIGHT_WORDS, w, re.IGNORECASE):
        return h + 12 if h >= 7 else h
    # No AM/PM word: in a question about outdoor work, 1-6 means afternoon, 7-11 morning, 12 noon.
    return h + 12 if 1 <= h <= 6 else h


def _named_day(question: str, now: datetime) -> str | None:
    """"today" / "tomorrow" if every weekday named is today's or tomorrow's, "other" if any other, else None.
    ("hôm nay (thứ Ba)" on a Tuesday is today, the way ClimateGuard's own alerts write it.)"""
    named = {i for names in WEEKDAYS.values() for i, n in enumerate(names)
             if re.search(rf"(?<!\w){re.escape(n)}(?!\w)", question, re.IGNORECASE)}
    if not named:
        return None
    today, tomorrow = now.weekday(), (now.weekday() + 1) % 7
    return "today" if named == {today} else "tomorrow" if named == {tomorrow} else "other"


def _clock_times(question: str, now: datetime) -> list[datetime]:
    """Every clock time in the question, as today's date at that time."""
    out = []
    for m in _TIME.finditer(question):
        if not any(m.group(g) for g in ("pre", "at", "sep", "post")):
            continue  # a bare number is not a time
        h = int(m.group("h"))  # int() also reads Arabic-Indic digits (٣)
        minute = 30 if m.group("m") in ("半", "반") else int(m.group("m") or 0)
        hour = _hour24(h, m.group("post"), m.group("pre"))
        if hour is not None:
            out.append(now.replace(hour=hour, minute=minute, second=0, microsecond=0))
    return out


def resolve(question: str, now: datetime) -> TimeRef | None:
    """`now` is the zone's local time (timezone-aware)."""
    question = _with_digits(question)
    day = _named_day(question, now)
    if OTHER_DAY.search(question) or day == "other":
        return None
    times = _clock_times(question, now)
    if not times:
        return None
    target, end = times[0], (times[1] if len(times) > 1 else None)
    if end is not None and end <= target:  # "from 10 to 2" without AM/PM words; else past midnight
        end += timedelta(hours=12) if end + timedelta(hours=12) > target else timedelta(days=1)
    shift = timedelta(days=1)
    if day == "tomorrow" or TOMORROW.search(question):
        return TimeRef(target + shift, passed=False, end=end and end + shift)
    if (end or target) <= now:
        return TimeRef(target + shift, passed=True, end=end and end + shift)
    return TimeRef(target, passed=False, end=end)


# --- the note, written in code in each language ---------------------------------------------

WEEKDAYS = {
    "en": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
    "es": ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"],
    "vi": ["thứ Hai", "thứ Ba", "thứ Tư", "thứ Năm", "thứ Sáu", "thứ Bảy", "Chủ Nhật"],
    "zh": ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"],
    "tl": ["Lunes", "Martes", "Miyerkoles", "Huwebes", "Biyernes", "Sabado", "Linggo"],
    "ko": ["월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일"],
    "ar": ["الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"],
}


def _h12(t: datetime) -> int:
    return t.hour % 12 or 12


def clock(t: datetime, lang: str) -> str:
    h, m = _h12(t), t.minute
    if lang == "en":
        return f"{h}:{m:02d} {'AM' if t.hour < 12 else 'PM'}" if m else f"{h} {'AM' if t.hour < 12 else 'PM'}"
    if lang == "vi":
        part = ("sáng" if 4 <= t.hour <= 10 else "trưa" if t.hour in (11, 12) else "chiều" if 13 <= t.hour <= 17
                else "tối" if 18 <= t.hour <= 21 else "đêm")
        return f"{h} giờ {m} {part}" if m else f"{h} giờ {part}"
    if lang == "es":
        part = "de la mañana" if t.hour < 12 else "de la tarde" if t.hour < 20 else "de la noche"
        return f"{h}:{m:02d} {part}" if m else f"{h} {part}"
    if lang == "zh":
        part = "上午" if t.hour < 12 else "中午" if t.hour == 12 else "下午" if t.hour < 18 else "晚上"
        return f"{part}{h}点{m}分" if m else f"{part}{h}点"
    if lang == "ko":
        return f"{'오전' if t.hour < 12 else '오후'} {h}시" + (f" {m}분" if m else "")
    if lang == "tl":
        part = "umaga" if t.hour < 12 else "tanghali" if t.hour == 12 else "hapon" if t.hour < 18 else "gabi"
        return f"alas-{h}:{m:02d} ng {part}" if m else f"alas-{h} ng {part}"
    if lang == "ar":
        return f"{h}:{m:02d} {'صباحًا' if t.hour < 12 else 'مساءً'}" if m else f"{h} {'صباحًا' if t.hour < 12 else 'مساءً'}"
    raise ValueError(lang)


def note(ref: TimeRef, lang: str) -> str | None:
    """First sentence of the answer when the asked time already passed today."""
    if not ref.passed:
        return None
    c, day = clock(ref.target, lang), WEEKDAYS[lang][ref.target.weekday()]
    if ref.end:
        c = f"{c}–{clock(ref.end, lang)}"
    return {
        "en": f"{c} today has already passed. This is the forecast for {c} tomorrow ({day}).",
        "es": f"{'La' if _h12(ref.target) == 1 else 'Las'} {c} de hoy ya {'pasó' if _h12(ref.target) == 1 else 'pasaron'}. "
              f"Este es el pronóstico para mañana ({day}) a {'la' if _h12(ref.target) == 1 else 'las'} {c}.",
        "vi": f"{c} hôm nay đã qua, đây là dự báo cho {c} ngày mai ({day}).",
        "zh": f"今天{c}已经过了，以下是明天（{day}）{c}的预报。",
        "tl": f"Lumipas na ang {c} ngayong araw. Ito ang forecast para sa {c} bukas ({day}).",
        "ko": f"오늘 {c}는 이미 지났습니다. 내일({day}) {c} 예보입니다.",
        "ar": f"لقد مضت الساعة {c} اليوم. هذه توقعات الساعة {c} غدًا ({day}).",
    }[lang]
