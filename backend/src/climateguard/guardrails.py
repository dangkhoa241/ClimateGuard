"""Wording guardrails shared by the agent (monitor.py) and automatic translation (translate.py).

Masks: N95 masks filter particles (wildfire smoke, dust, ash: PM2.5/PM10). They do nothing
against ozone, a gas, so recommending one on an ozone day gives false protection. Found in
the Vietnamese review: the Sept 6 2022 alert (ozone AQI 208) told people to wear an N95.
"""
import re

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


# Vietnamese time words are capitalized only at the start of a sentence ("Hôm nay (thứ Ba), ..."),
# never mid-sentence ("có hiệu lực hôm nay (thứ Bảy)"). Fixed in code, like temperatures.
_VI_TIME_MID_SENTENCE = re.compile(r"([^.!?:\s])(\s+)(Hôm nay|Tối nay|Sáng nay|Chiều nay|Đêm nay|Ngày mai)")


def fix_vi_case(text: str) -> str:
    return _VI_TIME_MID_SENTENCE.sub(lambda m: m.group(1) + m.group(2) + m.group(3).lower(), text)
