"""Offline tests for web push delivery: message content (title carries the official level name), the real pywebpush
call (TTL, urgency, VAPID, encryption) against a fake HTTP layer, pruning, email-first ordering, the time budget,
failure isolation, and that the private key never leaks."""
import base64
import json
import logging
import os
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from climateguard import config, notify, push_store, ratelimit, webpush, zones
from climateguard.languages import LANGS

ROOT = Path(__file__).resolve().parents[2]
ZONE = {"zone": "CAZ159", "name": "Central San Joaquin County", "place": "Stockton, CA", "tz": "America/Los_Angeles",
        "langs": ["en", "es", "vi"]}
EN_WARNING = "Excessive Heat Warning until 8 PM tonight. Temperatures reach 108°F. Stay in shade when you can."
MSG = {"en": EN_WARNING,
       "es": "Aviso de calor excesivo hasta las 8 PM de hoy. Las temperaturas llegan a 108°F. Busque la sombra.",
       "vi": "Cảnh báo nắng nóng cực độ đến 8 giờ tối nay. Nhiệt độ lên tới 108°F. Hãy ở trong bóng râm."}
FAKE_KEY = "FAKEPRIVATEKEYMARKER1234567890abcdefghijklmnopq"


def b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def new_vapid_private() -> str:
    key = ec.generate_private_key(ec.SECP256R1())
    return b64(key.private_numbers().private_value.to_bytes(32, "big"))


def device(n: int) -> dict:
    """A real subscriber key pair, as a browser would create (so encryption really runs)."""
    key = ec.generate_private_key(ec.SECP256R1())
    pub = key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    return {"endpoint": f"https://fcm.googleapis.com/fcm/send/dev{n}", "p256dh": b64(pub), "auth": b64(os.urandom(16))}


@pytest.fixture(autouse=True)
def local(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "LOCAL_DIR", tmp_path)
    monkeypatch.setattr(config, "STORAGE", "local")
    monkeypatch.setattr(config, "NOTIFY_MODE", "dryrun")
    monkeypatch.setattr(config, "FRONTEND_URL", "https://app.example")
    monkeypatch.setattr(config, "VAPID_PRIVATE_KEY", new_vapid_private())
    monkeypatch.setattr(ratelimit, "_local", {})
    monkeypatch.setattr(zones, "get", lambda z: dict(ZONE))


def subscribe_devices(n, lang="es", zone="CAZ159"):
    subs = [device(i) for i in range(n)]
    for s in subs:
        push_store.put(zone, lang, s)
    return subs


def texts(**extra):
    base = {lang: (MSG[lang], None) for lang in ("en", "es", "vi")}
    return {**base, **extra}


# --- message content ------------------------------------------------------------------------------------------

LEVEL_CASES = [
    ("Excessive Heat Warning until 8 PM.", "Warning"), ("Fire Weather Watch tomorrow.", "Watch"),
    ("Heat Advisory today. Drink water.", "Advisory"),
    ("A Heat Advisory is in effect, and a Fire Weather Watch starts tomorrow.", "Watch"),  # highest wins
    ("A Flood Watch and an Excessive Heat Warning are both active.", "Warning"),
]
LEVEL_WORDS = {
    "en": {"Warning": "Warning", "Watch": "Watch", "Advisory": "Advisory"},
    "es": {"Warning": "Aviso", "Watch": "Vigilancia", "Advisory": "Advertencia"},
    "vi": {"Warning": "Cảnh báo", "Watch": "Cảnh giác", "Advisory": "Khuyến cáo"},
    **{lang: {"Warning": "Warning", "Watch": "Watch", "Advisory": "Advisory"} for lang in ("zh", "tl", "ko", "ar")},
}


@pytest.mark.parametrize("lang", list(LANGS))
@pytest.mark.parametrize("english,level", LEVEL_CASES)
def test_title_always_contains_the_official_level_name(lang, english, level):
    """When the alert names an NWS level, the title carries it, in every language."""
    other = {"en": english, lang: ("translated text. second sentence.", True if lang in notify.AUTO_LABEL else None)}
    text, translated = other[lang] if lang != "en" else (english, None)
    p = webpush.build_payload(ZONE, lang, "heat", "high", text, translated, english)
    assert LEVEL_WORDS[lang][level] in p["title"], p["title"]


@pytest.mark.parametrize("lang", list(LANGS))
def test_title_is_the_email_subject_and_has_no_level_when_the_alert_has_none(lang):
    english = "Hot and dry weather today. Drink water often."
    p = webpush.build_payload(ZONE, lang, "heat", "high", "Texto. Otro.", None, english)
    subject, _ = notify.compose(ZONE, lang, "heat", "high", "Texto. Otro.", None)
    assert p["title"] == subject
    assert not any(w in p["title"] for w in ("Warning", "Watch", "Advisory", "Aviso", "Vigilancia", "Cảnh báo"))


def test_title_ends_with_the_exact_email_subject_when_a_level_is_added():
    p = webpush.build_payload(ZONE, "es", "heat", "high", MSG["es"], None, EN_WARNING)
    subject, _ = notify.compose(ZONE, "es", "heat", "high", MSG["es"], None)
    assert p["title"] == f"Aviso · {subject}"
    assert subject == "ClimateGuard: alerta de calor - Stockton, CA"


def test_level_is_not_repeated_when_the_subject_already_says_it(monkeypatch):
    monkeypatch.setitem(notify.SUBJECT, "en", "ClimateGuard {sev} {hazard} Warning - {place}")
    p = webpush.build_payload(ZONE, "en", "heat", "high", EN_WARNING, None, EN_WARNING)
    assert p["title"].count("Warning") == 1


def test_body_is_the_first_one_or_two_sentences_with_temperatures_as_in_email():
    p = webpush.build_payload(ZONE, "es", "heat", "high", MSG["es"], None, EN_WARNING)
    assert p["body"] == "Aviso de calor excesivo hasta las 8 PM de hoy. Las temperaturas llegan a 108°F (42°C)."
    assert "Busque la sombra" not in p["body"]


def test_long_first_sentence_is_cut_and_short_ones_are_kept_whole():
    long = "A" * 400 + ". Second."
    body = webpush.build_payload(ZONE, "en", "heat", "high", long, None, long)["body"]
    assert len(body) <= webpush.MAX_BODY_CHARS and body.endswith("…")
    two = webpush.first_sentences("One. Two. Three.")
    assert two == "One. Two."


def test_cjk_and_arabic_sentences_are_split():
    assert webpush.first_sentences("今天很热。请喝水。不要外出。") == "今天很热。 请喝水。"
    assert webpush.first_sentences("الجو حار. اشرب الماء. ابق في الظل.").count(".") == 2


@pytest.mark.parametrize("lang", ["zh", "tl", "ko", "ar"])
def test_machine_translated_languages_keep_the_automatic_translation_label(lang):
    translated = webpush.build_payload(ZONE, lang, "heat", "high", "text. more.", True, EN_WARNING)["body"]
    fallback = webpush.build_payload(ZONE, lang, "heat", "high", EN_WARNING, False, EN_WARNING)["body"]
    assert translated.endswith(notify.AUTO_LABEL[lang])
    assert fallback.endswith(notify.AUTO_FALLBACK[lang])
    for reviewed in ("en", "es", "vi"):
        assert not any(label in webpush.build_payload(ZONE, reviewed, "heat", "high", "x. y.", None, "x")["body"]
                       for label in notify.AUTO_LABEL.values())


def test_url_opens_the_alert_page_in_the_subscribers_language():
    for lang in LANGS:
        p = webpush.build_payload(ZONE, lang, "heat", "high", "x. y.", None, "x")
        assert p["url"] == f"https://app.example/?zone=CAZ159&lang={lang}" and p["lang"] == lang
        assert p["tag"] == "CAZ159-heat"


def test_payload_stays_small_and_has_no_advice_beyond_the_validated_text():
    p = webpush.build_payload(ZONE, "en", "heat", "high", "Hot. " * 400, None, "x")
    assert len(json.dumps(p, ensure_ascii=False).encode()) < 4000
    assert set(p) == {"title", "body", "lang", "tag", "url"}


# --- the real pywebpush call ---------------------------------------------------------------------------------------

def test_real_send_uses_ttl_6h_urgency_high_vapid_and_encrypts(monkeypatch):
    captured = {}

    class Resp:
        status_code = 201
        text = ""

    def fake_post(url, data=None, headers=None, timeout=None, **kw):
        captured.update(url=url, data=data, headers={k.lower(): v for k, v in headers.items()}, timeout=timeout)
        return Resp()

    monkeypatch.setattr("requests.post", fake_post)
    sub = device(1)
    payload = json.dumps({"title": "T", "body": "SECRET-BODY"})
    assert webpush._send(sub, payload, config.VAPID_PRIVATE_KEY) == 201
    h = captured["headers"]
    assert captured["url"] == sub["endpoint"]
    assert h["ttl"] == "21600" and h["urgency"] == "high"
    assert h["content-encoding"] == "aes128gcm" and h["authorization"].lower().startswith("vapid")
    assert b"SECRET-BODY" not in captured["data"]  # encrypted for the device
    assert captured["timeout"] == config.PUSH_TIMEOUT_S == 5


def test_real_send_maps_http_errors_to_status_codes(monkeypatch):
    from pywebpush import WebPushException

    class Resp:
        status_code = 410

    def gone(*a, **k):
        raise WebPushException("gone", response=Resp())

    monkeypatch.setattr("requests.post", gone)
    assert webpush._send(device(1), "{}", config.VAPID_PRIVATE_KEY) == 410

    def no_response(*a, **k):
        raise WebPushException("timeout")

    monkeypatch.setattr("requests.post", no_response)
    assert webpush._send(device(1), "{}", config.VAPID_PRIVATE_KEY) == 0


def test_ttl_is_six_hours():
    assert config.PUSH_TTL_S == 6 * 3600


# --- fan-out -----------------------------------------------------------------------------------------------------

@pytest.fixture
def sent(monkeypatch):
    calls = []

    def fake(sub, payload, key):
        calls.append((sub["endpoint"], json.loads(payload)))
        return 201

    monkeypatch.setattr(webpush, "_send", fake)
    return calls


def test_only_matching_zone_and_language_get_the_push(sent):
    mine = subscribe_devices(2, "es")
    push_store.put("CAZ159", "vi", {**device(50)})
    push_store.put("CAZ159", "ko", {**device(51)})        # a language with no alert in this run
    push_store.put("MNZ060", "es", {**device(52)})        # another zone
    result = webpush.send_for_zone(ZONE, "heat", "high", texts(), EN_WARNING)
    assert result == {"enabled": True, "sent": 3, "gone": 0, "failed": 0, "skipped": 0}
    endpoints = {c[0] for c in sent}
    assert endpoints == {s["endpoint"] for s in mine} | {"https://fcm.googleapis.com/fcm/send/dev50"}
    by_lang = {c[1]["lang"] for c in sent}
    assert by_lang == {"es", "vi"}


def test_each_subscriber_gets_their_own_language_and_url(sent):
    subscribe_devices(1, "es")
    webpush.send_for_zone(ZONE, "heat", "high", texts(), EN_WARNING)
    payload = sent[0][1]
    assert payload["body"].startswith("Aviso de calor") and payload["title"].startswith("Aviso · ")
    assert payload["url"].endswith("?zone=CAZ159&lang=es")


@pytest.mark.parametrize("status", [404, 410])
def test_gone_devices_are_removed_and_their_slot_freed(monkeypatch, status):
    subs = subscribe_devices(2, "es")
    ratelimit.claim_push_slot(500), ratelimit.claim_push_slot(500)
    monkeypatch.setattr(webpush, "_send", lambda s, p, k: status if s["endpoint"] == subs[0]["endpoint"] else 201)
    result = webpush.send_for_zone(ZONE, "heat", "high", texts(), EN_WARNING)
    assert (result["sent"], result["gone"]) == (1, 1)
    assert [r["endpoint"] for r in push_store.list_for("CAZ159", "es")] == [subs[1]["endpoint"]]
    assert push_store.get_pointer(subs[0]["endpoint"]) is None
    assert ratelimit.peek_counter("push-subscribers") == 1


@pytest.mark.parametrize("status", [0, 400, 401, 403, 413, 429, 500, 502, 503])
def test_other_failures_keep_the_subscription(monkeypatch, status):
    subs = subscribe_devices(1, "es")
    monkeypatch.setattr(webpush, "_send", lambda s, p, k: status)
    result = webpush.send_for_zone(ZONE, "heat", "high", texts(), EN_WARNING)
    assert (result["failed"], result["gone"]) == (1, 0)
    assert len(push_store.list_for("CAZ159", "es")) == 1 and subs


def test_one_device_raising_does_not_stop_the_others(monkeypatch):
    subs = subscribe_devices(3, "es")
    delivered = []

    def flaky(s, p, k):
        if s["endpoint"] == subs[1]["endpoint"]:
            raise RuntimeError("boom")
        delivered.append(s["endpoint"])
        return 201

    monkeypatch.setattr(webpush, "_send", flaky)
    result = webpush.send_for_zone(ZONE, "heat", "high", texts(), EN_WARNING)
    assert (result["sent"], result["failed"]) == (2, 1) and len(delivered) == 2


def test_without_a_vapid_key_push_is_off(monkeypatch, sent):
    monkeypatch.setattr(config, "VAPID_PRIVATE_KEY", "")
    monkeypatch.setattr(config, "VAPID_PRIVATE_KEY_PARAM", "")
    subscribe_devices(1, "es")
    assert webpush.send_for_zone(ZONE, "heat", "high", texts(), EN_WARNING) == {"enabled": False}
    assert sent == []


def test_key_is_read_from_ssm_in_lambda(monkeypatch):
    from climateguard import ssm

    monkeypatch.setattr(config, "VAPID_PRIVATE_KEY", "")
    monkeypatch.setattr(config, "VAPID_PRIVATE_KEY_PARAM", "/climateguard/vapid-private-key")
    asked = []
    monkeypatch.setattr(ssm, "get_secret", lambda name: asked.append(name) or "from-ssm")
    assert webpush.vapid_key() == "from-ssm" and asked == ["/climateguard/vapid-private-key"]


def test_unreadable_ssm_key_turns_push_off_quietly(monkeypatch, caplog):
    from climateguard import ssm

    monkeypatch.setattr(config, "VAPID_PRIVATE_KEY", "")
    monkeypatch.setattr(config, "VAPID_PRIVATE_KEY_PARAM", "/climateguard/vapid-private-key")
    monkeypatch.setattr(webpush, "_warned_no_key", False)

    def denied(name):
        raise RuntimeError("AccessDenied")

    monkeypatch.setattr(ssm, "get_secret", denied)
    assert webpush.vapid_key() is None


# --- emails first, push never blocks them -------------------------------------------------------------------------

def _outbox_lines():
    path = config.LOCAL_DIR / "outbox.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()] if path.exists() else []


@pytest.fixture
def no_translation(monkeypatch):
    monkeypatch.setattr(notify, "translate_alert", lambda text, lang: (f"[{lang}] {text}", True))


def test_every_email_is_published_before_any_push_starts(monkeypatch, no_translation):
    subscribe_devices(2, "es")
    seen = {}

    def spy(sub, payload, key):
        seen.setdefault("emails_at_first_push", len(_outbox_lines()))
        return 201

    monkeypatch.setattr(webpush, "_send", spy)
    zone = {**ZONE, "langs": ["en", "es", "vi", "zh"]}
    result = notify.deliver(zone, "heat", "high", MSG)
    assert seen["emails_at_first_push"] == 4  # all four language emails were already out
    assert result["push"]["sent"] == 2 and result["languages"] == ["en", "es", "vi", "zh"]


def test_push_raising_never_breaks_delivery(monkeypatch):
    subscribe_devices(1, "es")
    monkeypatch.setattr(webpush, "send_for_zone", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("push exploded")))
    result = notify.deliver(ZONE, "heat", "high", MSG)
    assert result["languages"] == ["en", "es", "vi"] and len(_outbox_lines()) == 3
    assert "push" not in result


def test_slow_push_service_cannot_hold_delivery_past_the_budget(monkeypatch):
    subscribe_devices(12, "es")
    monkeypatch.setattr(config, "PUSH_BUDGET_S", 0.4)
    monkeypatch.setattr(config, "PUSH_WORKERS", 2)
    monkeypatch.setattr(webpush, "_send", lambda s, p, k: time.sleep(3) or 201)  # every service hangs
    t0 = time.monotonic()
    result = notify.deliver(ZONE, "heat", "high", MSG)
    elapsed = time.monotonic() - t0
    assert elapsed < 1.5, f"push held delivery for {elapsed:.1f}s"
    assert len(_outbox_lines()) == 3                       # emails done
    assert result["push"]["sent"] == 0 and result["push"]["skipped"] == 12


def test_no_new_request_starts_after_the_budget(monkeypatch):
    subscribe_devices(6, "es")
    starts = []

    def slow(s, p, k):
        starts.append(s["endpoint"])
        time.sleep(0.25)
        return 201

    monkeypatch.setattr(config, "PUSH_WORKERS", 1)
    monkeypatch.setattr(webpush, "_send", slow)
    result = webpush.send_for_zone(ZONE, "heat", "high", texts(), EN_WARNING, budget_s=0.6)
    time.sleep(0.9)  # let the single worker drain: it must skip the rest, not send them
    assert len(starts) <= 4 and result["skipped"] >= 2


def test_default_budget_leaves_collect_plenty_of_headroom():
    assert config.PUSH_BUDGET_S <= 20 and config.PUSH_TIMEOUT_S <= 5
    template = (ROOT / "template.yaml").read_text(encoding="utf-8")
    assert re.search(r"CollectFunction:[\s\S]*?Timeout: 600", template)  # 20 s per alert vs a 600 s Lambda


def test_emails_and_push_do_not_change_when_no_one_subscribed_to_push(monkeypatch, no_translation):
    called = []
    monkeypatch.setattr(webpush, "_send", lambda *a: called.append(a) or 201)
    result = notify.deliver(ZONE, "heat", "high", MSG)
    assert called == [] and result["push"] == {"enabled": True, "sent": 0, "gone": 0, "failed": 0, "skipped": 0}


# --- secrets ----------------------------------------------------------------------------------------------------------

def test_private_key_never_reaches_logs_results_or_errors(monkeypatch, caplog):
    caplog.set_level(logging.DEBUG)
    monkeypatch.setattr(config, "VAPID_PRIVATE_KEY", FAKE_KEY)
    subscribe_devices(3, "es")
    statuses = iter([201, 410, 0])

    def sender(sub, payload, key):
        assert key == FAKE_KEY
        status = next(statuses)
        if status == 0:
            raise RuntimeError(f"failed with {sub['endpoint']}")  # a library error might mention anything
        return status

    monkeypatch.setattr(webpush, "_send", sender)
    result = webpush.send_for_zone(ZONE, "heat", "high", texts(), EN_WARNING)
    assert FAKE_KEY not in caplog.text and FAKE_KEY not in json.dumps(result)
    assert "fcm.googleapis.com" not in caplog.text  # endpoints are capabilities: never logged
    assert "p256dh" not in caplog.text


def test_repo_has_no_vapid_private_key_in_tracked_files():
    skip = {"node_modules", ".git", "dist", ".local", ".aws-sam", "__pycache__", ".pytest_cache", ".venv"}
    rx = re.compile(r"VAPID_PRIVATE_KEY(?!_PARAM)\s*[=:]\s*[\"']?[A-Za-z0-9_\-]{20,}")
    offenders = []
    for path in ROOT.rglob("*"):
        if path.is_dir() or skip & set(path.parts) or path.suffix in {".png", ".ico", ".gz", ".csv", ".json"}:
            continue
        if path.name == "test_webpush.py":
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if rx.search(text) or "BEGIN EC PRIVATE KEY" in text or "BEGIN PRIVATE KEY" in text:
            offenders.append(str(path.relative_to(ROOT)))
    assert offenders == []
    example = (ROOT / ".env.example").read_text(encoding="utf-8")
    assert "VAPID_PRIVATE_KEY" not in example
