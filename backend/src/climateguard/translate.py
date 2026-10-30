"""Automatic translation of validated English alerts (Muse Spark 1.3, Meta Model API).

Only for languages that have subscribers in the zone. Source text has already passed the
medical-wording and mask guardrails in English; the prompt forbids adding anything, and a
translation that adds mask advice is rejected in code. On any failure
the English message is sent instead, so an alert is never lost to a translation error.
"""
import logging

from . import budget, config, guardrails
from .languages import LANGS
from .llm import chat

log = logging.getLogger(__name__)
MAX_CHARS = 600

PROMPT = ("Translate this public-safety weather alert from English into {language}. Keep the same meaning, "
          "times and numbers, in short plain sentences a non-expert understands. Do not add, remove or soften "
          "any advice, and do not add medical information. Output only the translation.")


def translate_alert(text_en: str, lang: str, *, raise_on_spend_cap: bool = False) -> tuple[str, bool]:
    """Returns (text, translated); background delivery can fall back if the spend cap is reached."""
    try:
        res = chat("meta", config.CHAT_MODEL,
                   [{"role": "system", "content": PROMPT.format(language=LANGS[lang]["name"])},
                    {"role": "user", "content": text_en}],
                   max_tokens=1200, purpose=f"translate:{lang}")
        text = res.text.strip()
        if guardrails.mentions_mask(text) and not guardrails.mentions_mask(text_en):
            # e.g. "limit time outdoors" on an ozone day must never become "wear a mask"
            log.warning("translation to %s rejected (added mask advice the English doesn't have)", lang)
        elif text and len(text) <= MAX_CHARS:
            return text, True
        else:
            log.warning("translation to %s rejected (empty or too long)", lang)
    except budget.SpendCapExceeded:
        if raise_on_spend_cap:
            raise
        log.warning("translation to %s skipped because the daily model-spend cap was reached", lang)
    except Exception as e:  # missing key, API down, ...: never block the alert
        log.warning("translation to %s failed: %s", lang, e)
    return text_en, False
