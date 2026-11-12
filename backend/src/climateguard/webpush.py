"""Web push alerts: sent after the emails, inside a fixed time budget, and never able to break them.

For one sent alert, notify.deliver() calls send_for_zone() once every email is published. Each subscriber of the
zone gets the alert in their own language:
  title: the same subject line the email uses (notify.compose), with the official NWS level name (Warning, Watch or
         Advisory, in the subscriber's language) in front when the validated message names one
  body:  the first one or two sentences of the validated message (already through the medical-wording and
         level-name guardrails), temperatures as in the email; machine-translated languages keep the
         "automatic translation" label
  url:   the alert page in the subscriber's language (the same link the email carries)
No advice text is written here. Each push is sent with a 6-hour TTL and "high" urgency; a 404 or 410 from the push
service removes that subscription. Logs hold counts only, never endpoints, keys or the private key.
"""
import json
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor, wait

from . import config, push_store, ratelimit, ssm, units
from .guardrails import ES_LEVEL, VI_LEVEL

log = logging.getLogger(__name__)

MAX_BODY_CHARS = 160
MAX_PAYLOAD_BYTES = 3500  # push services allow about 4 KB
LEVELS = ("Warning", "Watch", "Advisory")  # highest first
_LEVEL_RX = re.compile(r"\b(Warning|Watch|Advisory)\b")
_SENTENCE_END = re.compile(r"(?<=[.!?。！？؟])\s*")
LEVEL_NAME = {"es": ES_LEVEL, "vi": VI_LEVEL}  # other languages keep the English NWS word (the official name)


# --- message ---------------------------------------------------------------------------------------------------

def official_level(english_text: str, lang: str) -> str | None:
    """The NWS level the validated message names (highest of Warning, Watch, Advisory), in `lang`."""
    found = set(_LEVEL_RX.findall(english_text or ""))
    for level in LEVELS:
        if level in found:
            return LEVEL_NAME.get(lang, {}).get(level, level)
    return None


def first_sentences(text: str, limit: int = MAX_BODY_CHARS) -> str:
    parts = [p.strip() for p in _SENTENCE_END.split(text.strip()) if p.strip()]
    body = ""
    for part in parts[:2]:
        joined = f"{body} {part}".strip()
        if body and len(joined) > limit:
            break
        body = joined
    return body if len(body) <= limit else body[: limit - 1].rstrip() + "…"


def build_payload(zone: dict, lang: str, hazard: str, severity: str, text: str, translated: bool | None,
                  english_text: str) -> dict:
    from . import notify  # notify imports this module lazily; keep the import here to avoid a cycle

    subject, _ = notify.compose(zone, lang, hazard, severity, text, translated)
    level = official_level(english_text, lang)
    title = f"{level} · {subject}" if level and level.lower() not in subject.lower() else subject
    body = first_sentences(units.format_temps(text, lang))
    if lang in notify.AUTO_LABEL:
        body = f"{body} {notify.AUTO_LABEL[lang] if translated else notify.AUTO_FALLBACK[lang]}"
    payload = {"title": title, "body": body, "lang": lang, "tag": f"{zone['zone']}-{hazard}",
               "url": f"{config.FRONTEND_URL}/?zone={zone['zone']}&lang={lang}"}
    while len(json.dumps(payload, ensure_ascii=False).encode()) > MAX_PAYLOAD_BYTES and len(payload["body"]) > 20:
        payload["body"] = payload["body"][: len(payload["body"]) // 2].rstrip() + "…"
    return payload


# --- sending ---------------------------------------------------------------------------------------------------

_warned_no_key = False


def vapid_key() -> str | None:
    """The VAPID private key: SSM SecureString in Lambda, or VAPID_PRIVATE_KEY for local development."""
    global _warned_no_key
    key = config.VAPID_PRIVATE_KEY
    if not key and config.VAPID_PRIVATE_KEY_PARAM:
        try:
            key = ssm.get_secret(config.VAPID_PRIVATE_KEY_PARAM)
        except Exception as e:  # never log the value; the error type is enough
            if not _warned_no_key:
                log.warning("web push is off: cannot read the VAPID key (%s)", type(e).__name__)
                _warned_no_key = True
    return key or None


def _send(subscription: dict, payload: str, key: str, contact: str | None = None) -> int:
    """One push request. Returns the HTTP status (0 if there was none: timeout, network error).
    `contact` is the VAPID "sub" claim (the app's URL by default)."""
    from pywebpush import WebPushException, webpush

    try:
        resp = webpush(subscription_info={"endpoint": subscription["endpoint"],
                                          "keys": {"p256dh": subscription["p256dh"], "auth": subscription["auth"]}},
                       data=payload, vapid_private_key=key, vapid_claims={"sub": contact or config.FRONTEND_URL},
                       ttl=config.PUSH_TTL_S, headers={"Urgency": "high"}, timeout=config.PUSH_TIMEOUT_S)
        return int(getattr(resp, "status_code", 201))
    except WebPushException as e:
        return int(getattr(getattr(e, "response", None), "status_code", 0) or 0)


def send_for_zone(zone: dict, hazard: str, severity: str, texts: dict, english_text: str,
                  budget_s: float | None = None) -> dict:
    """`texts`: {lang: (validated text, translated flag)}, as built for the emails. Returns counts only."""
    key = vapid_key()
    if not key:
        return {"enabled": False}
    budget = config.PUSH_BUDGET_S if budget_s is None else budget_s
    started = time.monotonic()
    jobs = []
    for lang, (text, translated) in texts.items():
        subs = push_store.list_for(zone["zone"], lang)
        if subs:
            payload = json.dumps(build_payload(zone, lang, hazard, severity, text, translated, english_text),
                                 ensure_ascii=False)
            jobs += [(lang, s, payload) for s in subs]
    counts = {"enabled": True, "sent": 0, "gone": 0, "failed": 0, "skipped": 0}
    if not jobs:
        return counts

    def one(job):
        lang, sub, payload = job
        if time.monotonic() - started > budget:
            return job, None  # out of time: never start another request
        try:
            return job, _send(sub, payload, key)
        except Exception as e:  # a bug or a library error for one device must not stop the rest
            log.warning("push send error: %s", type(e).__name__)
            return job, 0

    pool = ThreadPoolExecutor(max_workers=max(1, config.PUSH_WORKERS))
    futures = [pool.submit(one, j) for j in jobs]
    done, pending = wait(futures, timeout=max(0.0, budget - (time.monotonic() - started)))
    pool.shutdown(wait=False, cancel_futures=True)  # requests already in flight end on their own (5 s timeout)
    counts["skipped"] += len(pending)
    for f in done:
        if f.cancelled():
            counts["skipped"] += 1
            continue
        (lang, sub, _), status = f.result()
        if status is None:
            counts["skipped"] += 1
        elif 200 <= status < 300:
            counts["sent"] += 1
        elif status in (404, 410):  # the device unsubscribed or uninstalled: forget it
            counts["gone"] += 1
            try:
                push_store.delete_subscriber(zone["zone"], lang, push_store.endpoint_hash(sub["endpoint"]))
                ratelimit.release_push_slot()
            except Exception:
                log.exception("could not remove a gone push subscription")
        else:
            counts["failed"] += 1
    log.info("web push for %s %s: sent=%d gone=%d failed=%d skipped=%d", zone["zone"], hazard, counts["sent"],
             counts["gone"], counts["failed"], counts["skipped"])
    return counts
