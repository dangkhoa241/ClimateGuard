"""Translate the app's English screen text into zh/tl/ko/ar with Muse Spark 1.3 (automatic, labeled in the app).

Reads REVIEWED_STRINGS.en from frontend/src/strings.js (via node), writes frontend/src/i18n.auto.json.
Checks in code, per language: the same keys, the same {placeholders} in every string, and the names and
numbers that must never change (ClimateGuard, 911, 211, N95, WhatsApp, OSHA, °F...). One retry with the
problems listed. About $0.02 per language.

Usage:  python scripts/translate_ui.py            # all four
        python scripts/translate_ui.py ko ar      # some
Rerun after changing English strings; EN/ES/VI stay human-written in strings.js.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

import _path  # noqa: F401

from climateguard.languages import LANGS
from climateguard.llm import chat

FRONTEND = Path(__file__).resolve().parents[2] / "frontend" / "src"
OUT = FRONTEND / "i18n.auto.json"
TARGETS = ("zh", "tl", "ko", "ar")
KEEP = ("ClimateGuard", "911", "211", "N95", "WhatsApp", "OSHA", "NOAA", "ZIP", "AWS", "°F", "§3395", "§5141.1")
PLACEHOLDER = re.compile(r"\{\w+\}")

PROMPT = """Translate the VALUES of this JSON into {language} for a mobile safety app used by farmworkers and immigrant families in the United States.
Rules:
- Keep every key and the JSON structure exactly; translate only the string values.
- Keep placeholders like {{place}}, {{time}}, {{n}}, {{cost}} exactly as they are.
- Keep these unchanged: ClimateGuard, 911, 211, N95, WhatsApp, OSHA, Cal/OSHA, NOAA, ZIP, AWS, "Confirm subscription", °F, T8 §3395, T8 §5141.1, and "$".
- Plain, simple, polite words that a non-expert understands. Short, like app buttons and labels.
- The "severity" values are the app's own risk levels (moderate / high / extreme risk): never use the words your language uses for National Weather Service "Warning", "Watch" or "Advisory".
- "Wireless Emergency Alerts" is the phone setting: use the name iPhone/Android show in {language}.
Return only the JSON, no code fences, no comments."""


def english() -> dict:
    url = (FRONTEND / "strings.js").as_uri()
    js = f"const m = await import({json.dumps(url)}); process.stdout.write(JSON.stringify(m.REVIEWED_STRINGS.en))"
    out = subprocess.run(["node", "--input-type=module", "-e", js], capture_output=True, text=True, encoding="utf-8",
                         check=True)
    return json.loads(out.stdout)


def problems(src: dict, dst: dict, path: str = "") -> list[str]:
    out = []
    for k, v in src.items():
        where = f"{path}{k}"
        if k not in dst:
            out.append(f"missing key {where}")
        elif isinstance(v, dict):
            out += problems(v, dst[k] if isinstance(dst[k], dict) else {}, where + ".")
        elif not isinstance(dst[k], str) or not dst[k].strip():
            out.append(f"{where} is empty")
        else:
            if sorted(PLACEHOLDER.findall(v)) != sorted(PLACEHOLDER.findall(dst[k])):
                out.append(f"{where}: placeholders changed ({PLACEHOLDER.findall(v)})")
            out += [f"{where}: '{w}' missing" for w in KEEP if w in v and w not in dst[k]]
    out += [f"extra key {path}{k}" for k in dst if k not in src]
    return out


def translate(src: dict, lang: str) -> dict:
    messages = [{"role": "system", "content": PROMPT.format(language=LANGS[lang]["name"])},
                {"role": "user", "content": json.dumps(src, ensure_ascii=False, indent=1)}]
    for attempt in range(2):
        res = chat("meta", "muse-spark-1.3", messages, max_tokens=16000, reasoning_effort="low", deadline_s=240,
                   use_cache=False, purpose=f"translate-ui:{lang}")
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", res.text.strip())
        try:
            dst = json.loads(text)
            issues = problems(src, dst)
        except json.JSONDecodeError as e:
            dst, issues = None, [f"not valid JSON: {e}"]
        print(f"  {lang} attempt {attempt + 1}: {len(issues)} problem(s), ${res.cost_usd:.4f}")
        if not issues:
            return dst
        messages += [{"role": "assistant", "content": res.text},
                     {"role": "user", "content": "Fix these problems and return the full JSON again:\n- "
                                                 + "\n- ".join(issues[:40])}]
    raise SystemExit(f"{lang}: still {len(issues)} problem(s): {issues[:10]}")


def main(argv: list[str]) -> None:
    langs = [a for a in argv if a in TARGETS] or list(TARGETS)
    src = english()
    current = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    for lang in langs:
        print(f"Translating {len(src)} keys into {LANGS[lang]['name']}...")
        current[lang] = translate(src, lang)
        OUT.write_text(json.dumps(current, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main(sys.argv[1:])
