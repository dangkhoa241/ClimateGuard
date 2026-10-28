"""Temperature formatting for alert text, done in code (never by the model).

  English:       "114F" / "114 F" / "114 °F"            -> "114°F"
  other langs:   "114F" / "114 độ F" / "114 grados F"   -> "114°F (46°C)"
Idempotent: text that already has "(46°C)" is left alone, so it can run at every stage.
"""
import re

# a number, optional space, optional "°" / "độ" / "grados", then F as a whole word,
# not already followed by a Celsius value in parentheses
_TEMP_F = re.compile(r"(?<![\w.])(-?\d{1,3})\s?(?:°\s?|độ\s|grados\s)?F\b(?!\s*\(\s*-?\d{1,3}\s*°\s*C\))",
                     re.IGNORECASE)


def to_celsius(f: float) -> int:
    return round((f - 32) * 5 / 9)


def format_temps(text: str, lang: str) -> str:
    def repl(m: re.Match) -> str:
        f = int(m.group(1))
        return f"{f}°F" if lang == "en" else f"{f}°F ({to_celsius(f)}°C)"
    return _TEMP_F.sub(repl, text)
