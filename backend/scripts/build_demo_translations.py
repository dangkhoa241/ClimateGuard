"""Generate and back-check static translations for the saved demo replay alerts."""
import json
from pathlib import Path

import _path  # noqa: F401

from climateguard import demo, guardrails
from climateguard.languages import LANGS, REVIEWED
from climateguard.llm import chat
from climateguard.monitor import MEDICAL_TERMS

MODEL = "muse-spark-1.3"
TARGETS = ("es", "vi", "zh", "tl", "ko", "ar")
OUT = Path(__file__).resolve().parents[1] / "src" / "climateguard" / "data" / "demo_translations.json"
BACKCHECK_PROMPT = """Check translations of public-safety weather alerts. For each event and hazard, translate
each listed language back into English as literally as possible and compare meaning with source_en.
Set match=false only for a material difference in time, number, place, hazard, severity, or protective action.
Do not add medical advice. Return JSON only with the same event/hazard nesting, and each target language as
{"back_translation":"...","match":true,"issues":[]}."""


def sources() -> dict:
    return {
        event: {
            alert["hazard"]: alert["messages"]
            for alert in demo.saved()[event]["sent"]
        }
        for event in demo.DEMO_MOMENTS
    }


def parse_json(text: str) -> dict:
    decoder = json.JSONDecoder()
    for index, character in enumerate(text):
        if character == "{":
            try:
                value, _ = decoder.raw_decode(text[index:])
                if isinstance(value, dict):
                    return value
            except json.JSONDecodeError:
                continue
    raise ValueError("model did not return a JSON object")


def translate_language(lang: str, inputs: dict) -> dict:
    prompt = (
        f"Translate each English public-safety alert into {LANGS[lang]['name']}. Keep the meaning, "
        "times, numbers, places and every protective action. Use short, clear wording. Do not add, omit, "
        "weaken or reverse advice. Never add medical advice. Only the wildfire-smoke alert may mention "
        "an N95 mask, and only if the English source already says so. Return JSON with identical event and "
        "hazard keys and translated string values, with no other text."
    )
    messages = [{"role": "system", "content": prompt},
                {"role": "user", "content": json.dumps(inputs, ensure_ascii=False)}]
    for attempt in range(2):
        response = chat("meta", MODEL, messages, max_tokens=5000, reasoning_effort="low",
                        deadline_s=240, use_cache=False, purpose=f"demo-fixture-translation:{lang}")
        translated = parse_json(response.text)
        problems = []
        for event, alerts in translated.items():
            for hazard, text in alerts.items():
                original = sources()[event][hazard]["en"]
                if not isinstance(text, str) or not text.strip() or len(text) > 600:
                    problems.append(f"{event}/{hazard}/{lang}: empty or too long")
                elif MEDICAL_TERMS.search(text):
                    problems.append(f"{event}/{hazard}/{lang}: medical wording")
                elif guardrails.mentions_mask(text) and not guardrails.mentions_mask(original):
                    problems.append(f"{event}/{hazard}/{lang}: added mask advice")
                if "N95" in str(text).upper() and (event != "smoke_2020" or hazard != "smoke"):
                    problems.append(f"{event}/{hazard}/{lang}: N95 outside wildfire-smoke replay")
        shape_problems = []
        if set(translated) != set(inputs):
            shape_problems.append("event keys changed")
        for event, alerts in inputs.items():
            if event not in translated or set(translated[event]) != set(alerts):
                shape_problems.append(f"{event}: hazard keys changed")
        if shape_problems:
            problems.extend(shape_problems)
        print(f"{lang} attempt {attempt + 1}: ${response.cost_usd:.4f}; {len(problems)} issue(s)")
        if not problems:
            return translated
        messages.extend([
            {"role": "assistant", "content": response.text},
            {"role": "user", "content": "Fix these issues and return the complete JSON:\n- "
             + "\n- ".join(problems)},
        ])
    raise ValueError(f"{lang} translation failed validation: {problems}")


def backcheck(fixtures: dict) -> dict:
    payload = {}
    for event, alerts in fixtures.items():
        payload[event] = {}
        for hazard, translations in alerts.items():
            payload[event][hazard] = {
                "source_en": translations["en"],
                **{lang: translations[lang] for lang in TARGETS},
            }
    response = chat(
        "meta", MODEL,
        [{"role": "system", "content": BACKCHECK_PROMPT},
         {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
        max_tokens=8000, reasoning_effort="low", deadline_s=240, use_cache=False,
        purpose="demo-fixture-backcheck",
    )
    print(f"Back-translation model cost: ${response.cost_usd:.4f}")
    return parse_json(response.text)


def main() -> None:
    source = sources()
    fixtures = {}
    for event, alerts in source.items():
        fixtures[event] = {}
        for hazard, messages in alerts.items():
            fixtures[event][hazard] = {"en": messages["en"]}
            fixtures[event][hazard].update({lang: messages[lang] for lang in REVIEWED if lang != "en"})

    inputs = {event: {hazard: messages["en"] for hazard, messages in alerts.items()}
              for event, alerts in source.items()}
    generated = {}
    for lang in ("zh", "tl", "ko", "ar"):
        translated = translate_language(lang, inputs)
        for event, alerts in translated.items():
            for hazard, text in alerts.items():
                generated.setdefault(event, {}).setdefault(hazard, {})[lang] = text

    for event, alerts in generated.items():
        for hazard, translations in alerts.items():
            fixtures[event][hazard].update(translations)

    checks = backcheck(fixtures)
    mismatches = []
    for event, alerts in fixtures.items():
        for hazard, translations in alerts.items():
            check = checks.get(event, {}).get(hazard, {})
            for lang in TARGETS:
                result = check.get(lang) or {}
                if not result.get("match"):
                    mismatches.append((event, hazard, lang, result.get("issues") or ["no confirmed match"]))
    print(f"Back-translation checks: {sum(len(a) * len(TARGETS) for a in fixtures.values()) - len(mismatches)} "
          f"matched; {len(mismatches)} mismatch(es).")
    for event, hazard, lang, issues in mismatches:
        print(f"MISMATCH {event}/{hazard}/{lang}: {', '.join(issues)}")

    OUT.write_text(json.dumps(fixtures, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"Saved static fixtures to {OUT}")


if __name__ == "__main__":
    main()
