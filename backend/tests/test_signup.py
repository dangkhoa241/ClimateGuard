"""Offline tests for sign-up by zone + language, rate limits, subscriber cap, email
composition in 7 languages (auto-translation labeled), SNS topics, confirmed counts."""
import base64
import json
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest

from climateguard import alerts_store, config, notify, ratelimit, subscriptions, zones
from climateguard.handlers import api
from climateguard.languages import LANGS

MN = {"zone": "MNZ060", "name": "Hennepin", "state": "MN", "county": "MNC053", "fire_zone": "MNZ060",
      "tz": "America/Chicago", "office": "MPX", "lat": 44.98, "lon": -93.27, "place": "Minneapolis, MN",
      "forecast_hourly": "x", "demo": False}


@pytest.fixture(autouse=True)
def local(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "LOCAL_DIR", tmp_path)
    monkeypatch.setattr(config, "STORAGE", "local")
    monkeypatch.setattr(config, "NOTIFY_MODE", "dryrun")
    monkeypatch.setattr(ratelimit, "_local", {})
    monkeypatch.setattr(zones, "resolve_point", lambda lat, lon: dict(MN))  # no NWS calls in tests


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


SIGNUP = {"email": "maria@example.com", "zip": "95202", "lang": "es"}  # Stockton demo zone, no network


# --- sign-up ---

def test_signup_by_zip_returns_zone_and_not_covered_note():
    status, body = _post(SIGNUP)
    assert status == 202 and body["zone"] == "CAZ159" and body["lang"] == "es"
    assert "Wireless Emergency Alerts" in body["not_covered"]
    [rec] = _outbox()
    assert rec["zone"] == "CAZ159" and "maria" not in json.dumps(rec)  # email stored only as a hash
    assert zones.get("CAZ159")["langs"] == ["es"]


def test_signup_by_browser_location_anywhere_in_us():
    status, body = _post({"email": "a@example.com", "lat": 44.9778, "lon": -93.265, "lang": "ko"})
    assert status == 202 and body["zone"] == "MNZ060" and body["place"] == "Minneapolis, MN"


def test_signup_base64_body():
    assert _post(SIGNUP, b64=True)[0] == 202


@pytest.mark.parametrize("change,code", [
    ({"email": "not-an-email"}, "invalid_email"), ({"email": ""}, "invalid_email"),
    ({"lang": "fr"}, "invalid_lang"), ({"zip": None}, "missing_location"),
    ({"zip": "12ab5"}, "invalid_zip"), ({"zip": None, "lat": 51.5, "lon": -0.12}, "outside_us"),
])
def test_signup_validation(change, code):
    assert _post({**SIGNUP, **change}) == (400, {"error": code})


def test_all_seven_languages_accepted():
    for i, lang in enumerate(LANGS):
        assert _post({**SIGNUP, "email": f"u{i}@example.com", "lang": lang}, ip=f"10.1.0.{i}")[0] == 202
    assert zones.get("CAZ159")["langs"] == sorted(LANGS)


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


def test_rate_limit_applies_before_any_location_lookup(monkeypatch):
    for i in range(subscriptions.PER_IP_PER_HOUR):
        _post({**SIGNUP, "email": f"x{i}@example.com"})
    monkeypatch.setattr(zones, "locate", lambda **k: pytest.fail("blocked requests must not look up a zone"))
    assert _post({**SIGNUP, "email": "late@example.com"})[0] == 429


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

ZONE = dict(zones.DEMO_ZONES["CAZ159"], langs=["en", "es", "vi"])


@pytest.mark.parametrize("lang", list(LANGS))
def test_compose_every_language(lang):
    subject, body = notify.compose(ZONE, lang, "winter", "extreme", "MESSAGE", translated=True)
    assert subject.isascii() and len(subject) < 100 and "Stockton" in subject
    assert "MESSAGE" in body and "911" in body and f"zone=CAZ159&lang={lang}" in body
    if not LANGS[lang]["reviewed"]:
        assert notify.AUTO_LABEL[lang] in body  # machine translation is always labeled


@pytest.mark.parametrize("hazard", ["heat", "cold", "winter", "flood", "coastal", "tornado", "thunderstorm",
                                    "tropical", "wind", "fire", "smoke", "dust", "fog", "other"])
def test_subjects_exist_for_every_hazard_group(hazard):
    for lang in ("en", "es", "vi", "tl"):
        assert hazard in notify.HAZARD_SUBJECT[lang]


def test_every_email_states_what_climateguard_does_not_cover():
    for lang in ("en", "es", "vi", "ko"):
        _, body = notify.compose(ZONE, lang, "heat", "high", "M", translated=True)
        assert "911" in body and ("Wireless Emergency Alerts" in body or "NOAA" in body)


def test_deliver_reviewed_text_and_labeled_translations(monkeypatch):
    seen = []
    monkeypatch.setattr(notify, "translate_alert", lambda text, lang: seen.append(lang) or (f"[{lang}] {text}", True))
    msgs = {"en": "Heat today.", "es": "Calor hoy.", "vi": "Nắng nóng hôm nay."}
    out = notify.deliver(dict(ZONE, langs=["es", "ko", "zh"]), "heat", "high", msgs)
    assert out["languages"] == ["es", "ko", "zh"] and seen == ["ko", "zh"]  # only non-reviewed are translated
    bodies = {r["lang"]: r["body"] for r in _outbox() if r["type"] == "alert"}
    assert bodies["es"].startswith("Calor hoy.")
    assert bodies["ko"].startswith(notify.AUTO_LABEL["ko"]) and "[ko] Heat today." in bodies["ko"]


def test_translation_failure_falls_back_to_english_with_note(monkeypatch):
    monkeypatch.setattr(notify, "translate_alert", lambda text, lang: (text, False))
    out = notify.deliver(dict(ZONE, langs=["ar"]), "heat", "high", {"en": "Heat today.", "es": "x", "vi": "y"})
    [body] = [r["body"] for r in _outbox() if r["type"] == "alert"]
    assert out["translations"] == {"ar": "english_fallback"}
    assert body.startswith(notify.AUTO_FALLBACK["ar"]) and "Heat today." in body


def test_zone_without_signups_publishes_reviewed_languages():
    out = notify.deliver(dict(ZONE, langs=[]), "heat", "high", {"en": "e", "es": "s", "vi": "v"})
    assert out["languages"] == ["en", "es", "vi"]


# --- SNS (fake client) ---

class FakeSNS:
    def __init__(self):
        self.calls, self.subs = [], {}

    def create_topic(self, Name, **kw):
        self.calls.append(("create_topic", Name))
        return {"TopicArn": f"arn:aws:sns:us-east-2:123:{Name}"}

    def subscribe(self, **kw):
        self.calls.append(("subscribe", kw))
        return {"SubscriptionArn": "pending confirmation"}

    def publish(self, **kw):
        self.calls.append(("publish", kw))
        return {"MessageId": "m1"}

    def list_subscriptions_by_topic(self, TopicArn, **kw):
        return {"Subscriptions": self.subs.get(TopicArn, [])}


@pytest.fixture
def sns(monkeypatch):
    fake = FakeSNS()
    monkeypatch.setitem(sys.modules, "boto3", types.SimpleNamespace(client=lambda name: fake))
    monkeypatch.setattr(config, "NOTIFY_MODE", "sns")
    subscriptions.topic_arn.cache_clear()
    yield fake
    subscriptions.topic_arn.cache_clear()


def test_sns_subscribe_uses_zone_language_topic(sns):
    assert _post(SIGNUP)[0] == 202
    sub = next(kw for name, kw in sns.calls if name == "subscribe")
    assert sub == {"TopicArn": "arn:aws:sns:us-east-2:123:climateguard-caz159-es",
                   "Protocol": "email", "Endpoint": "maria@example.com"}


def test_sns_publish_only_to_languages_with_signups(sns, monkeypatch):
    monkeypatch.setattr(notify, "translate_alert", lambda text, lang: (text, True))
    notify.deliver(dict(ZONE, langs=["en", "tl"]), "smoke", "high", {"en": "e", "es": "s", "vi": "v"})
    pubs = [kw for name, kw in sns.calls if name == "publish"]
    assert [p["TopicArn"].rsplit(":", 1)[1] for p in pubs] == ["climateguard-caz159-en", "climateguard-caz159-tl"]
    assert all(p["Subject"].isascii() for p in pubs)


def test_refresh_confirmed_counts_only_confirmed_subscriptions(sns):
    zones.put({**MN, "langs": ["en", "ko"], "confirmed": 0})
    arn = "arn:aws:sns:us-east-2:123:climateguard-mnz060-"
    sns.subs = {arn + "en": [{"SubscriptionArn": "arn:aws:sns:us-east-2:123:t:1"},
                             {"SubscriptionArn": "PendingConfirmation"}],
                arn + "ko": [{"SubscriptionArn": "arn:aws:sns:us-east-2:123:t:2"}]}
    assert subscriptions.refresh_confirmed(max_age_minutes=0) == ["MNZ060"]
    assert zones.get("MNZ060")["confirmed"] == 2
    assert "MNZ060" in [z["zone"] for z in zones.monitored()]
    assert subscriptions.refresh_confirmed() == []  # fresh count: not rechecked within the hour


# --- recent alerts endpoint ---

def test_zone_alerts_endpoint_newest_first():
    alerts_store.record_sent("CAZ159", "heat", "high", {"en": "1", "es": "1", "vi": "1"}, "r")
    alerts_store.record_sent("CAZ159", "smoke", "high", {"en": "2", "es": "2", "vi": "2"}, "r")
    r = api.handler({"routeKey": "GET /zones/{zone}/alerts", "pathParameters": {"zone": "caz159"}}, None)
    rows = json.loads(r["body"])
    assert r["statusCode"] == 200 and len(rows) == 2 and rows[0]["sent_at"] >= rows[1]["sent_at"]
    bad = api.handler({"routeKey": "GET /zones/{zone}/alerts", "pathParameters": {"zone": "x"}}, None)
    assert bad["statusCode"] == 404
