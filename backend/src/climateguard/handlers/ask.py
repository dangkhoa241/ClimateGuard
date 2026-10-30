"""Lambda (HTTP API): POST /ask {question, lang, zone} -> an answer in the person's language,
POST /transcribe?lang= (a spoken question as WAV) -> its text, POST /pretalk (supervisor view),
and POST /demo/replay {event, lang} (demo mode: a real past event through the monitoring agent).

Its own function (not api.py) because it calls a model: longer timeout, model-key access.
Per-IP rate limits; the daily model budget is checked in ask.answer().
"""
import base64
import logging

from .. import alerts_store, ask, budget, demo, llm, pretalk, ratelimit, transcribe
from ..languages import LANGS
from ..translate import translate_alert
from ..subscriptions import SignupError
from .api import ZONE_RE, _json_body, _resp, _source_ip

log = logging.getLogger()
ASK_PER_IP_PER_HOUR = 20
PRETALK_PER_IP_PER_HOUR = 10
DEMO_REPLAYS_PER_IP_PER_HOUR = 15  # a fresh run is about $0.015; repeats within an hour are cached
TRANSCRIBE_PER_IP_PER_HOUR = 30  # at most 60 s each: under $0.10/hour per IP
TRANSLATE_PER_IP_PER_HOUR = 10
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


def post_translate(event) -> dict:
    """Translate a known English alert for an existing alert card, on an explicit retry."""
    try:
        body = _json_body(event)
    except SignupError as e:
        return _resp(e.status, {"error": e.code})
    lang = str(body.get("lang") or "")
    zone = str(body.get("zone") or "").upper()
    hazard = str(body.get("hazard") or "")
    sent_at = str(body.get("sent_at") or "")
    if lang not in LANGS or lang == "en":
        return _resp(400, {"error": "invalid_lang"})
    if not ZONE_RE.match(zone) or not hazard or not sent_at:
        return _resp(400, {"error": "invalid_alert"})
    if not ratelimit.hit("translate-ip", _source_ip(event), TRANSLATE_PER_IP_PER_HOUR, 3600):
        return _resp(429, {"error": "rate_limited"}, headers={"Retry-After": "3600"})
    alert = next((row for row in alerts_store.recent_sent(zone, hours=48)
                  if row.get("hazard") == hazard and row.get("ts") == sent_at), None)
    if alert is None:
        return _resp(404, {"error": "unknown_alert"})
    text, translated = translate_alert(alert["messages"]["en"], lang)
    if not translated:
        return _resp(502, {"error": "translation_unavailable"})
    return _resp(200, {"text": text, "lang": lang})

def post_pretalk(event) -> dict:
    """POST /pretalk {zone, lang}: today's crew checklist + an AI pre-shift talk (supervisor view)."""
    try:
        body = _json_body(event)
    except SignupError as e:
        return _resp(e.status, {"error": e.code})
    lang, zone = str(body.get("lang") or ""), str(body.get("zone") or "").upper()
    if lang not in LANGS:
        return _resp(400, {"error": "invalid_lang"})
    if not ZONE_RE.match(zone):
        return _resp(400, {"error": "unknown_zone"})
    if not ratelimit.hit("pretalk-ip", _source_ip(event), PRETALK_PER_IP_PER_HOUR, 3600):
        return _resp(429, {"error": "rate_limited"}, headers={"Retry-After": "3600"})
    snap = ask.zone_snapshot(zone)
    if snap is None:
        return _resp(404, {"error": "unknown_zone"})
    if budget.over_budget():  # the checklist still works without the model
        items = pretalk.render(pretalk.checklist(snap), lang)
        return _resp(200, {"today": pretalk.today(snap), "checklist": items, "kind": "checklist_only",
                           "talk": " ".join(i["text"] for i in items), "reason": "budget",
                           "checklist_lang": lang if lang in pretalk.REVIEWED else "en",
                           "automatic": lang not in pretalk.REVIEWED})
    result = pretalk.build(snap, lang)
    log.info("pretalk zone=%s lang=%s kind=%s blocked=%s", zone, lang, result["kind"], result.get("blocked"))
    return _resp(200, result)


def post_demo_replay(event) -> dict:
    """Demo mode: replay a real event through the live agent (never emailed). Over the rate limit or the
    daily budget, the person still gets an answer: the earlier saved run, labeled with why."""
    try:
        body = _json_body(event)
    except SignupError as e:
        return _resp(e.status, {"error": e.code})
    name, lang = str(body.get("event") or ""), str(body.get("lang") or "")
    if name not in demo.DEMO_MOMENTS:
        return _resp(400, {"error": "unknown_event"})
    if lang not in LANGS:
        return _resp(400, {"error": "invalid_lang"})
    if not ratelimit.hit("demo-ip", _source_ip(event), DEMO_REPLAYS_PER_IP_PER_HOUR, 3600):
        return _resp(200, demo.saved_result(name, lang, "rate_limited"))
    if budget.over_budget():
        return _resp(200, demo.saved_result(name, lang, "budget"))
    result = demo.run(name, lang)
    log.info("demo replay event=%s lang=%s source=%s why=%s cost=%s", name, lang, result["source"],
             result["why"], result["decision"]["cost_usd"])
    return _resp(200, result)


def handler(event, context):
    if event.get("routeKey") == "POST /demo/replay":
        return post_demo_replay(event)
    if event.get("routeKey") == "POST /ask":
        return post_ask(event)
    if event.get("routeKey") == "POST /transcribe":
        return post_transcribe(event)
    if event.get("routeKey") == "POST /translate":
        return post_translate(event)
    if event.get("routeKey") == "POST /pretalk":
        return post_pretalk(event)
    return _resp(404, {"error": "not found"})
