"""Offline tests for Phase 3: sign-up, rate limits, subscriber cap, email composition, SNS calls."""
import base64
import json
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest

from climateguard import alerts_store, config, notify, ratelimit, subscriptions
from climateguard.handlers import api


@pytest.fixture(autouse=True)
def local(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "LOCAL_DIR", tmp_path)
    monkeypatch.setattr(config, "STORAGE", "local")
    monkeypatch.setattr(config, "NOTIFY_MODE", "dryrun")
    monkeypatch.setattr(ratelimit, "_local", {})


def _outbox():
    path = config.LOCAL_DIR / "outbox.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()] if path.exists() else []


def _post(body, ip="1.2.3.4", b64=False):
    raw = json.dumps(body) if not isinstance(body, str) else body
    if b64:
        raw = base64.b64encode(raw.encode()).decode()
    r = api.handler({"routeKey": "POST /subscribe", "body": raw, "isBase64Encoded": b64,
                     "requestContext": {"http": {"sourceIp": ip}}}, None)
    return r["statusCode"], json.loads(r["body"])


SIGNUP = {"email": "maria@example.com", "city": "stockton", "lang": "es"}


# --- sign-up ---

def test_signup_accepted_and_email_not_stored_in_plain_text():
    assert _post(SIGNUP) == (202, {"status": "pending_confirmation", "city": "stockton", "lang": "es"})
    [rec] = _outbox()
    assert rec["type"] == "subscribe" and rec["lang"] == "es" and "maria" not in json.dumps(rec)


def test_signup_base64_body():
    assert _post(SIGNUP, b64=True)[0] == 202


@pytest.mark.parametrize("field,value,code", [
    ("email", "not-an-email", "invalid_email"), ("email", "", "invalid_email"),
    ("city", "fresno", "invalid_city"), ("lang", "fr", "invalid_lang"),
])
def test_signup_validation(field, value, code):
    assert _post({**SIGNUP, field: value}) == (400, {"error": code})


def test_bad_bodies():
    assert _post("{not json")[0] == 400
    assert _post("[1, 2]")[0] == 400
    assert _post({**SIGNUP, "pad": "x" * 3000})[0] == 413


def test_honeypot_pretends_success_but_does_nothing():
    assert _post({**SIGNUP, "website": "http://spam.example"})[0] == 202
    assert _outbox() == []


# --- rate limits and cap ---

def test_per_ip_limit():
    for i in range(subscriptions.PER_IP_PER_HOUR):
        assert _post({**SIGNUP, "email": f"user{i}@example.com"})[0] == 202
    status, body = _post({**SIGNUP, "email": "one-more@example.com"})
    assert (status, body["error"]) == (429, "rate_limited")
    assert _post({**SIGNUP, "email": "other-ip@example.com"}, ip="5.6.7.8")[0] == 202


def test_per_email_limit_across_ips():
    for i in range(subscriptions.PER_EMAIL_PER_DAY):
        assert _post(SIGNUP, ip=f"10.0.0.{i}")[0] == 202
    assert _post(SIGNUP, ip="10.0.0.99")[0] == 429


def test_subscriber_cap(monkeypatch):
    monkeypatch.setattr(config, "MAX_SUBSCRIBERS", 2)
    assert _post({**SIGNUP, "email": "a@example.com"}, ip="1.1.1.1")[0] == 202
    assert _post({**SIGNUP, "email": "b@example.com"}, ip="1.1.1.2")[0] == 202
    assert _post({**SIGNUP, "email": "c@example.com"}, ip="1.1.1.3") == (503, {"error": "subscriber_cap"})
    # a rejected address stays rejected on retry (it must not be remembered as "already subscribed")
    assert _post({**SIGNUP, "email": "c@example.com"}, ip="1.1.1.4") == (503, {"error": "subscriber_cap"})
    # an existing subscriber re-requesting confirmation doesn't count against the cap
    assert _post({**SIGNUP, "email": "a@example.com"}, ip="1.1.1.5")[0] == 202
    assert ratelimit.peek_counter("subscribers") == 2


# --- email composition + delivery ---

@pytest.mark.parametrize("lang", ["en", "es", "vi"])
def test_compose_subject_ascii_and_footer(lang):
    subject, body = notify.compose("stockton", lang, "heat", "extreme", "MESSAGE")
    assert subject.isascii() and len(subject) < 100 and "Stockton" in subject
    assert body.startswith("MESSAGE") and "911" in body and f"city=stockton&lang={lang}" in body
    assert {"en": "unsubscribe", "es": "cancelar la suscripción", "vi": "hủy đăng ký"}[lang] in body


def test_deliver_dryrun_one_message_per_language():
    msgs = {"en": "Heat today.", "es": "Calor hoy.", "vi": "Nắng nóng hôm nay."}
    assert notify.deliver("lodi", "heat", "high", msgs)["languages"] == ["en", "es", "vi"]
    out = [r for r in _outbox() if r["type"] == "alert"]
    assert [(r["lang"], r["body"].split("\n")[0]) for r in out] == [(k, v) for k, v in msgs.items()]


class FakeSNS:
    def __init__(self):
        self.calls = []

    def create_topic(self, Name, **kw):
        self.calls.append(("create_topic", Name))
        return {"TopicArn": f"arn:aws:sns:us-west-2:123:{Name}"}

    def subscribe(self, **kw):
        self.calls.append(("subscribe", kw))
        return {"SubscriptionArn": "pending confirmation"}

    def publish(self, **kw):
        self.calls.append(("publish", kw))
        return {"MessageId": "m1"}


@pytest.fixture
def sns(monkeypatch):
    fake = FakeSNS()
    monkeypatch.setitem(sys.modules, "boto3", types.SimpleNamespace(client=lambda name: fake))
    monkeypatch.setattr(config, "NOTIFY_MODE", "sns")
    subscriptions.topic_arn.cache_clear()
    yield fake
    subscriptions.topic_arn.cache_clear()


def test_sns_subscribe_uses_city_language_topic(sns):
    assert _post(SIGNUP)[0] == 202
    sub = next(kw for name, kw in sns.calls if name == "subscribe")
    assert sub == {"TopicArn": "arn:aws:sns:us-west-2:123:climateguard-stockton-es",
                   "Protocol": "email", "Endpoint": "maria@example.com"}


def test_sns_publish_per_language_topic(sns):
    notify.deliver("stockton", "smoke", "high", {"en": "e", "es": "s", "vi": "v"})
    pubs = [kw for name, kw in sns.calls if name == "publish"]
    assert [p["TopicArn"].rsplit("-", 1)[1] for p in pubs] == ["en", "es", "vi"]
    assert all(p["Subject"].isascii() for p in pubs)


# --- recent alerts endpoint ---

def test_city_alerts_endpoint_newest_first():
    alerts_store.record_sent("stockton", "heat", "high", {"en": "1", "es": "1", "vi": "1"}, "r")
    alerts_store.record_sent("stockton", "smoke", "high", {"en": "2", "es": "2", "vi": "2"}, "r")
    r = api.handler({"routeKey": "GET /cities/{city}/alerts", "pathParameters": {"city": "stockton"}}, None)
    rows = json.loads(r["body"])
    assert r["statusCode"] == 200 and len(rows) == 2 and rows[0]["sent_at"] >= rows[1]["sent_at"]
    bad = api.handler({"routeKey": "GET /cities/{city}/alerts", "pathParameters": {"city": "x"}}, None)
    assert bad["statusCode"] == 404
