"""Lambda (HTTP API): POST /ask {question, lang, zone} -> an answer in the person's language,
and POST /transcribe?lang= (a spoken question as WAV) -> its text.

Its own function (not api.py) because it calls a model: longer timeout, model-key access.
Per-IP rate limits; the daily model budget is checked in ask.answer().
"""
import base64
import logging

from .. import ask, llm, ratelimit, transcribe
from ..languages import LANGS
from ..subscriptions import SignupError
from .api import ZONE_RE, _json_body, _resp, _source_ip

log = logging.getLogger()
ASK_PER_IP_PER_HOUR = 20
TRANSCRIBE_PER_IP_PER_HOUR = 30  # at most 60 s each: under $0.10/hour per IP
# 60 s of 16 kHz mono 16-bit audio is ~1.9 MB, ~2.6 MB as base64 (HTTP API payloads go up to 10 MB)
MAX_AUDIO_BODY_CHARS = 2_700_000

# Cold start: create the model client (OpenAI SDK import + API key from SSM) during Lambda init,
# which runs once per instance with a full CPU, instead of inside the first person's request.
try:
    llm._client("meta")
except Exception as e:  # no key yet, SSM down...: the request path retries and falls back
    log.warning("model client not ready at init: %s", e)


def post_ask(event) -> dict:
    try:
        body = _json_body(event)
    except SignupError as e:
        return _resp(e.status, {"error": e.code})
    question = str(body.get("question") or "").strip()
    lang = str(body.get("lang") or "")
    zone = str(body.get("zone") or "").upper()
    if not question or len(question) > ask.MAX_QUESTION_CHARS:
        return _resp(400, {"error": "invalid_question"})
    if lang not in LANGS:
        return _resp(400, {"error": "invalid_lang"})
    if not ZONE_RE.match(zone):
        return _resp(400, {"error": "unknown_zone"})
    if not ratelimit.hit("ask-ip", _source_ip(event), ASK_PER_IP_PER_HOUR, 3600):
        return _resp(429, {"error": "rate_limited"}, headers={"Retry-After": "3600"})
    result = ask.answer(question, lang, zone)
    log.info("ask zone=%s lang=%s kind=%s blocked=%s", zone, lang, result["kind"], result.get("blocked"))
    return _resp(200, result)


def post_transcribe(event) -> dict:
    """POST /transcribe?lang=vi, body = the WAV itself (API Gateway passes it base64-encoded)."""
    lang = str((event.get("queryStringParameters") or {}).get("lang") or "")
    if lang not in LANGS:
        return _resp(400, {"error": "invalid_lang"})
    raw = event.get("body") or ""
    if len(raw) > MAX_AUDIO_BODY_CHARS:
        return _resp(413, {"error": "audio_too_long"})
    if not ratelimit.hit("transcribe-ip", _source_ip(event), TRANSCRIBE_PER_IP_PER_HOUR, 3600):
        return _resp(429, {"error": "rate_limited"}, headers={"Retry-After": "3600"})
    try:
        data = base64.b64decode(raw) if event.get("isBase64Encoded") else raw.encode("latin-1")
        result = transcribe.transcribe(data, lang)
    except transcribe.AudioError as e:
        return _resp(e.status, {"error": e.code})
    except Exception as e:  # API down or slow: the person can still type the question
        log.warning("transcribe failed: %s", e)
        return _resp(502, {"error": "transcribe_failed"})
    log.info("transcribe lang=%s audio_ms=%s chars=%s", lang, result["audio_ms"], len(result["text"]))
    return _resp(200, result)


def handler(event, context):
    if event.get("routeKey") == "POST /ask":
        return post_ask(event)
    if event.get("routeKey") == "POST /transcribe":
        return post_transcribe(event)
    return _resp(404, {"error": "not found"})
