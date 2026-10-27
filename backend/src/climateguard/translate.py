"""Automatic translation of validated English alerts (Muse Spark 1.3, Meta Model API).

Only for languages that have subscribers in the zone. Source text has already passed the
medical-wording guardrail in English; the prompt forbids adding anything. On any failure
the English message is sent instead, so an alert is never lost to a translation error.
"""
import logging

from . import config
from .languages import LANGS
from .llm import chat

log = logging.getLogger(__name__)
MAX_CHARS = 600

PROMPT = ("Translate this public-safety weather alert from English into {language}. Keep the same meaning, "
          "times and numbers, in short plain sentences a non-expert understands. Do not add, remove or soften "
          "any advice, and do not add medical information. Output only the translation.")


def translate_alert(text_en: str, lang: str) -> tuple[str, bool]:
    """Returns (text, translated). translated=False means the English fallback was used."""
    try:
        res = chat("meta", config.CHAT_MODEL,
                   [{"role": "system", "content": PROMPT.format(language=LANGS[lang]["name"])},
                    {"role": "user", "content": text_en}],
                   max_tokens=1200, purpose=f"translate:{lang}")
        text = res.text.strip()
        if text and len(text) <= MAX_CHARS:
            return text, True
        log.warning("translation to %s rejected (empty or too long)", lang)
    except Exception as e:  # missing key, API down, ...: never block the alert
        log.warning("translation to %s failed: %s", lang, e)
    return text_en, False
