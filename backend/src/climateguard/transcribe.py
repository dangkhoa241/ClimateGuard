"""Voice questions: speech to text with Muse Voice Transcribe (Meta Model API).

The phone records the question, converts it to a 16 kHz mono 16-bit WAV (the only format the API
accepts) and posts it. The text goes back into the question box, where the person can check and
fix it before asking: Ask itself only ever sees text, with all its guardrails.

Endpoint (https://dev.meta.ai/docs/speech-to-text): POST /v1/asr/transcribe, multipart with a JSON
`request` part and an `audio` WAV part; $0.18 per hour of audio. Measured: a 4.4 s question took 2.6 s.
"""
import io
import json
import logging
import wave

import requests

from . import config, llm, usage

log = logging.getLogger(__name__)

MAX_AUDIO_SECONDS = 60     # a spoken question; also keeps the upload ~2 MB
CALL_TIMEOUT_S = 20        # API Gateway HTTP APIs stop at 30 s
SAMPLE_RATES = (16000, 24000)
# The API's language names for languageBias. English is added for the others: people mix in
# English place names and words ("AQI", "Stockton").
BIAS = {"en": "English", "es": "Spanish", "vi": "Vietnamese", "zh": "Mandarin Chinese", "tl": "Tagalog",
        "ko": "Korean", "ar": "Arabic"}
KEYWORDS = ["AQI", "N95", "ClimateGuard"]


class AudioError(ValueError):
    def __init__(self, code: str, status: int = 400):
        super().__init__(code)
        self.code, self.status = code, status


def check_wav(data: bytes) -> int:
    """Return the duration in ms, or raise AudioError if the API wouldn't accept the file."""
    try:
        with wave.open(io.BytesIO(data)) as w:
            ok = w.getnchannels() == 1 and w.getsampwidth() == 2 and w.getframerate() in SAMPLE_RATES
            ms = w.getnframes() * 1000 // max(w.getframerate(), 1)
    except (wave.Error, EOFError):
        raise AudioError("invalid_audio") from None
    if not ok:
        raise AudioError("invalid_audio")
    if ms < 300:
        raise AudioError("audio_too_short")
    if ms > MAX_AUDIO_SECONDS * 1000:
        raise AudioError("audio_too_long")
    return ms


def transcribe(data: bytes, lang: str) -> dict:
    """{text, audio_ms}. Raises AudioError for bad audio; other failures are the caller's fallback."""
    check_wav(data)
    bias = [BIAS[lang]] + (["English"] if lang != "en" else [])
    req = {"mode": "PUSH_TO_TALK", "model": config.TRANSCRIBE_MODEL, "audioEncoding": "WAV",
           "languageBias": bias, "keywords": KEYWORDS}
    key = llm._client("meta").api_key  # same key (env or SSM) as the chat calls
    r = requests.post(f"{config.META_BASE_URL}/asr/transcribe", headers={"Authorization": f"Bearer {key}"},
                      files={"request": (None, json.dumps(req), "application/json"),
                             "audio": ("question.wav", data, "audio/wav")},
                      timeout=CALL_TIMEOUT_S)
    if r.status_code in (400, 413):
        raise AudioError("invalid_audio")
    r.raise_for_status()
    body = r.json()
    audio_ms = int(body.get("audioDurationMs") or 0)
    usage.log_audio(config.TRANSCRIBE_MODEL, audio_ms, purpose=f"transcribe:{lang}")
    return {"text": (body.get("transcript") or "").strip(), "audio_ms": audio_ms}
