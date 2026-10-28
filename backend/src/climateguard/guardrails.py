"""Wording guardrails shared by the agent (monitor.py) and automatic translation (translate.py).

Masks: N95 masks filter particles (wildfire smoke, dust, ash: PM2.5/PM10). They do nothing
against ozone, a gas, so recommending one on an ozone day gives false protection. Found in
the Vietnamese review: the Sept 6 2022 alert (ozone AQI 208) told people to wear an N95.
"""
import re
import unicodedata

# "mask" in any of the 7 alert languages (en/tl "mask", es, vi, zh, ko, ar) plus N95/respirator
MASK_TERMS = re.compile(r"mask|\bN95\b|respirator|mascarill|cubreboca|tapaboca|m[aá]scara|kh[aẩ]u trang|"
                        r"口罩|마스크|كمام|قناع", re.IGNORECASE)
_PARTICLES = {"PM2.5", "PM10"}
_PARTICLE_WORDS = re.compile(r"smok|particle|PM2\.?5|PM10|\bdust|\bash\b|ashfall", re.IGNORECASE)
UNHEALTHY_FOR_SENSITIVE = 101


def mentions_mask(text: str) -> bool:
    return bool(MASK_TERMS.search(text or ""))


def particle_pollution(snapshot: dict) -> bool:
    """True when the air problem includes particles (masks can help): PM2.5/PM10 AQI 101+ now or
    forecast, a smoke/dust NWS alert about particles, or smoke in the hourly forecast. High ozone at
    the same time doesn't change this: masks still help with the smoke."""
    aqi = snapshot.get("aqi") or {}
    cur = aqi.get("current") or {}
    if max(cur.get("pm25_aqi") or 0, cur.get("pm10_aqi") or 0) >= UNHEALTHY_FOR_SENSITIVE:
        return True
    readings = [cur, *(aqi.get("forecast") or [])]
    if any(r.get("particles_unhealthy") for r in readings):
        return True
    if any(str(r.get("pollutant", "")).upper() in _PARTICLES and (r.get("aqi") or 0) >= UNHEALTHY_FOR_SENSITIVE
           for r in readings):
        return True
    for a in snapshot.get("alerts", []):
        if a.get("hazard") == "dust" or (a.get("hazard") == "smoke" and _PARTICLE_WORDS.search(
                " ".join(str(a.get(k) or "") for k in ("event", "headline", "description")))):
            return True
    return any("smoke" in str(h.get("short") or "").lower() for h in (snapshot.get("forecast") or {}).get("hours", []))


# --- reviewer's wording decisions (round 3), found by the eval's back-translation check ---

# Vietnamese AQI category wording, from the AQI value. "rất có hại" had been used for Unhealthy (157-185).
VI_AQI_PHRASES = {1: "có hại cho nhóm nhạy cảm", 2: "có hại cho sức khỏe", 3: "rất có hại cho sức khỏe",
                  4: "nguy hiểm cho sức khỏe"}
_AQI_NUMBER = re.compile(r"AQI\D{0,20}?(\d{2,3})", re.IGNORECASE)


def aqi_level(aqi: int) -> int:
    """0 Good/Moderate, 1 Unhealthy for Sensitive Groups, 2 Unhealthy, 3 Very Unhealthy, 4 Hazardous."""
    return 0 if aqi <= 100 else 1 if aqi <= 150 else 2 if aqi <= 200 else 3 if aqi <= 300 else 4


def _vi(text: str) -> str:
    # one spelling for comparisons: composed characters, "khỏe" (not "khoẻ"), lowercase
    return unicodedata.normalize("NFC", text).replace("khoẻ", "khỏe").lower()


def vi_aqi_wording_issue(text: str, fallback_aqi: int | None) -> str | None:
    """The strongest AQI category phrase in a Vietnamese message must match the highest AQI it states
    (or, with no number, the highest AQI in the data). Only for messages about air quality."""
    low = _vi(text)
    if "aqi" not in low and "không khí" not in low:
        return None
    used = {lvl for lvl, p in VI_AQI_PHRASES.items() if p in low}
    if 2 in used and low.count(VI_AQI_PHRASES[2]) == low.count(VI_AQI_PHRASES[3]):
        used.discard(2)  # every "có hại cho sức khỏe" was part of "rất có hại cho sức khỏe"
    if not used:
        return None
    numbers = [int(n) for n in _AQI_NUMBER.findall(text)]
    aqi = max(numbers) if numbers else fallback_aqi
    if aqi is None:
        return None
    expected = aqi_level(aqi)
    if max(used) == expected:
        return None
    want = f'"{VI_AQI_PHRASES[expected]}"' if expected else "no health-category phrase (AQI 100 or below)"
    return (f'Vietnamese AQI category wording: AQI {aqi} needs {want}, but the message says '
            f'"{VI_AQI_PHRASES[max(used)]}". Use: 101-150 "{VI_AQI_PHRASES[1]}", 151-200 "{VI_AQI_PHRASES[2]}", '
            f'201-300 "{VI_AQI_PHRASES[3]}", 301+ "{VI_AQI_PHRASES[4]}"')


# Spanish "en/por la tarde" is the afternoon, the hottest time: never as the time for outdoor work.
_ES_AFTERNOON_WORK = re.compile(
    r"(trabaj|labor|actividad|ejercicio|esfuerzo|tarea)[^.;]{0,80}\b(en|por|a) la tarde\b|"
    r"\b(en|por|a) la tarde\b[^.;]{0,80}(trabaj|labor|actividad|ejercicio|esfuerzo|tarea)", re.IGNORECASE)


def es_afternoon_work_issue(text: str) -> str | None:
    if _ES_AFTERNOON_WORK.search(text):
        return ('Spanish: "en la tarde" means afternoon, the hottest time; for work advice write '
                '"temprano en la mañana o al anochecer"')
    return None


# Vietnamese NWS level names: Warning "Cảnh báo", Watch "Cảnh giác", Advisory "Khuyến cáo".
VI_LEVEL = {"Warning": "Cảnh báo", "Watch": "Cảnh giác", "Advisory": "Khuyến cáo"}


def is_warning_level(event: str) -> bool:
    """Warnings and NWS "Alert" products (e.g. Air Quality Alert) may be called "Cảnh báo"."""
    return ("Warning" in event or "Alert" in event) and "Watch" not in event and "Advisory" not in event


def vi_level_issue(text: str, events: list[str]) -> str | None:
    """`events`: active NWS events for the alert's hazard. "Cảnh báo" only when one is a warning."""
    if "cảnh báo" not in _vi(text) or any(is_warning_level(e) for e in events):
        return None
    have = ", ".join(f'{e} = "{VI_LEVEL[k]}"' for e in events for k in ("Watch", "Advisory") if k in e)
    return ('Vietnamese alert level: no NWS warning is active for this hazard'
            + (f" ({have})" if have else " (no NWS alert at all)")
            + ', so never write "Cảnh báo". Watch = "Cảnh giác", Advisory = "Khuyến cáo"'
            + ("" if have else "; with no NWS alert, name no alert level"))


def vi_past_morning_issue(text: str, hour_now: int) -> str | None:
    """After noon, "sáng nay" is already past: a time after midnight is "rạng sáng [weekday]"."""
    if hour_now >= 12 and "sáng nay" in _vi(text):
        return ('Vietnamese time: "sáng nay" is already past at this hour; for a time after midnight write '
                '"rạng sáng [weekday]", e.g. "2 giờ rạng sáng thứ Hai"')
    return None


# Vietnamese time words are capitalized only at the start of a sentence ("Hôm nay (thứ Ba), ..."),
# never mid-sentence ("có hiệu lực hôm nay (thứ Bảy)"). Fixed in code, like temperatures.
_VI_TIME_MID_SENTENCE = re.compile(r"([^.!?:\s])(\s+)(Hôm nay|Tối nay|Sáng nay|Chiều nay|Đêm nay|Ngày mai)")


def fix_vi_case(text: str) -> str:
    return _VI_TIME_MID_SENTENCE.sub(lambda m: m.group(1) + m.group(2) + m.group(3).lower(), text)
