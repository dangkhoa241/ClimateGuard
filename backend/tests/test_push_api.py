"""Offline tests for web push sign-up: validation (including endpoint look-alikes), limits and caps, one
subscription per device, unsubscribe by endpoint, and push-only zones becoming monitored."""
import base64
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest

from climateguard import config, push_store, ratelimit, subscriptions, zones
from climateguard.handlers import api

MN = {"zone": "MNZ060", "name": "Hennepin", "state": "MN", "county": "MNC053", "fire_zone": "MNZ060",
      "tz": "America/Chicago", "office": "MPX", "lat": 44.98, "lon": -93.27, "place": "Minneapolis, MN",
      "forecast_hourly": "x", "demo": False}
FCM = "https://fcm.googleapis.com/fcm/send/abc123"


def b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def sub(endpoint=FCM, p256dh=None, auth=None):
    return {"endpoint": endpoint, "keys": {"p256dh": p256dh or b64(b"\x04" + os.urandom(64)),
                                           "auth": auth or b64(os.urandom(16))}}


@pytest.fixture(autouse=True)
def local(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "LOCAL_DIR", tmp_path)
    monkeypatch.setattr(config, "STORAGE", "local")
    monkeypatch.setattr(config, "NOTIFY_MODE", "dryrun")
    monkeypatch.setattr(ratelimit, "_local", {})
    monkeypatch.setattr(zones, "resolve_point", lambda lat, lon: dict(MN))


def call(route, body, ip="1.2.3.4"):
    raw = body if isinstance(body, str) else json.dumps(body)
    r = api.handler({"routeKey": route, "body": raw, "requestContext": {"http": {"sourceIp": ip}}}, None)
    return r["statusCode"], json.loads(r["body"]), r["headers"]


def subscribe(s=None, lang="es", ip="1.2.3.4", **extra):
    return call("POST /push/subscribe", {"subscription": s or sub(), "lang": lang, "zip": "95202", **extra}, ip)


# --- endpoint allow-list ----------------------------------------------------------------------------------------

@pytest.mark.parametrize("endpoint", [
    "https://fcm.googleapis.com/fcm/send/abc",
    "https://updates.push.services.mozilla.com/wpush/v2/abc",
    "https://web.push.apple.com/QAbc",
    "https://api.push.apple.com/3/device/abc",
    "https://wns2-par02p.notify.windows.com/w/?token=abc",
    "https://FCM.GOOGLEAPIS.COM/fcm/send/abc",  # host names are case-insensitive
])
def test_real_push_services_are_accepted(endpoint):
    assert push_store.validate_endpoint(endpoint) == endpoint


@pytest.mark.parametrize("endpoint", [
    "http://fcm.googleapis.com/fcm/send/abc",                 # not HTTPS
    "ftp://fcm.googleapis.com/x",
    "https://fcm.googleapis.com.evil.com/x",                  # allowed name as a prefix of another domain
    "https://evilfcm.googleapis.com/x",                       # glued onto the name, no dot
    "https://xpush.apple.com/x",
    "https://notapple.com/x",
    "https://push.apple.com.evil.com/x",
    "https://notify.windows.com.evil.io/x",
    "https://evil.com/fcm.googleapis.com",                    # allowed name in the path
    "https://evil.com/?h=fcm.googleapis.com",                 # ... or the query
    "https://evil.com#@fcm.googleapis.com/x",                 # ... or after a fragment
    "https://fcm.googleapis.com@evil.com/x",                  # user-info trick: the real host is evil.com
    "https://user:pw@fcm.googleapis.com/x",                   # credentials
    "https://fcm.googleapis.com:8443/x",                      # port
    "https://fcm.googleapis.com./x",                          # trailing dot
    "https://evil.com\\@fcm.googleapis.com/x",                # backslash
    "https://fcm.googleapis.com/x y",                         # whitespace
    "https://fcm.googleapis.com/x\n",
    "https://127.0.0.1/x", "https://169.254.169.254/latest/meta-data", "https://[::1]/x", "https://localhost/x",
    "https://fcm.googleаpis.com/x",                           # Cyrillic "а"
    "//fcm.googleapis.com/x", "fcm.googleapis.com/x", "", "https://", "https:///x",
    "https://fcm.googleapis.com/" + "a" * 700,                # over-length
])
def test_lookalike_and_unsafe_endpoints_are_rejected(endpoint):
    with pytest.raises(push_store.PushError):
        push_store.validate_endpoint(endpoint)


@pytest.mark.parametrize("value", [None, 5, [], {}, ["https://fcm.googleapis.com/x"]])
def test_non_string_endpoint_rejected(value):
    with pytest.raises(push_store.PushError):
        push_store.validate_endpoint(value)


def test_key_sizes_are_checked():
    bad = [
        sub(p256dh=b64(b"\x04" + os.urandom(63))),            # too short
        sub(p256dh=b64(b"\x05" + os.urandom(64))),            # not an uncompressed P-256 point
        sub(auth=b64(os.urandom(15))), sub(auth=b64(os.urandom(17))),
        sub(p256dh="not base64!!"), {"endpoint": FCM, "keys": {"p256dh": sub()["keys"]["p256dh"], "auth": ""}},
        {"endpoint": FCM}, {"endpoint": FCM, "keys": []}, {"keys": sub()["keys"]}, "text", None,
    ]
    for s in bad:
        with pytest.raises(push_store.PushError):
            push_store.validate_subscription(s)
    assert push_store.validate_subscription(sub())["endpoint"] == FCM


# --- the routes --------------------------------------------------------------------------------------------------

def test_subscribe_stores_one_device_for_zone_and_language():
    status, body, _ = subscribe()
    assert status == 201 and body["zone"] == "CAZ159" and body["lang"] == "es"
    assert body["not_covered"]
    h = push_store.endpoint_hash(FCM)
    rows = push_store.list_for("CAZ159", "es")
    assert len(rows) == 1 and rows[0]["endpoint"] == FCM
    assert push_store.get_pointer(FCM)["target_zone"] == "CAZ159"
    assert "CAZ159" in zones.get("CAZ159")["zone"] and "es" in zones.get("CAZ159")["langs"]
    assert h in rows[0]["sk"]


def test_response_never_echoes_the_endpoint_or_keys():
    s = sub()
    text = json.dumps(call("POST /push/subscribe", {"subscription": s, "lang": "en", "zip": "95202"})[1])
    assert FCM not in text and s["keys"]["auth"] not in text and s["keys"]["p256dh"] not in text


def test_subscribing_again_from_the_same_device_replaces_it():
    s = sub()
    subscribe(s, lang="es")
    subscribe(s, lang="vi")
    assert push_store.list_for("CAZ159", "es") == []
    assert len(push_store.list_for("CAZ159", "vi")) == 1
    assert ratelimit.peek_counter("push-subscribers") == 1  # still one slot


def test_changing_place_moves_the_subscription():
    s = sub()
    subscribe(s)
    status, body, _ = call("POST /push/subscribe", {"subscription": s, "lang": "es", "lat": 44.98, "lon": -93.27})
    assert status == 201 and body["zone"] == "MNZ060"
    assert push_store.list_for("CAZ159", "es") == []
    assert len(push_store.list_for("MNZ060", "es")) == 1


def test_unsubscribe_needs_the_endpoint_and_removes_everything():
    s = sub()
    subscribe(s)
    assert call("POST /push/unsubscribe", {"zone": "CAZ159", "lang": "es"})[0] == 400  # zone and language are not enough
    assert len(push_store.list_for("CAZ159", "es")) == 1
    status, body, _ = call("POST /push/unsubscribe", {"endpoint": FCM})
    assert status == 200 and body == {"status": "unsubscribed"}
    assert push_store.list_for("CAZ159", "es") == [] and push_store.get_pointer(FCM) is None
    assert ratelimit.peek_counter("push-subscribers") == 0


def test_unsubscribe_gives_the_same_answer_for_unknown_endpoints():
    assert call("POST /push/unsubscribe", {"endpoint": "https://fcm.googleapis.com/fcm/send/never-seen"})[:2] == (
        200, {"status": "unsubscribed"})
    assert ratelimit.peek_counter("push-subscribers") == 0  # a stranger's request never frees a slot
    assert call("POST /push/unsubscribe", {"endpoint": "https://evil.com/x"})[0] == 400


def test_unsubscribing_does_not_touch_another_device():
    subscribe(sub(FCM))
    subscribe(sub("https://fcm.googleapis.com/fcm/send/other"))
    call("POST /push/unsubscribe", {"endpoint": FCM})
    remaining = push_store.list_for("CAZ159", "es")
    assert [r["endpoint"] for r in remaining] == ["https://fcm.googleapis.com/fcm/send/other"]


@pytest.mark.parametrize("body", [
    {"lang": "es", "zip": "95202"},                                    # no subscription
    {"subscription": "x", "lang": "es", "zip": "95202"},
    {"subscription": sub(), "lang": "xx", "zip": "95202"},             # unknown language
    {"subscription": sub(), "lang": "es"},                             # no location
    {"subscription": sub("https://evil.com/x"), "lang": "es", "zip": "95202"},
])
def test_invalid_requests_are_400_and_store_nothing(body):
    assert call("POST /push/subscribe", body)[0] == 400
    assert push_store.list_for("CAZ159", "es") == []


def test_bad_json_and_oversized_bodies():
    assert call("POST /push/subscribe", "{nope")[0] == 400
    assert call("POST /push/subscribe", "[]")[0] == 400
    assert call("POST /push/subscribe", json.dumps({"x": "a" * 3000}))[0] == 413
    assert call("POST /push/unsubscribe", "{nope")[0] == 400


def test_honeypot_pretends_success_and_stores_nothing():
    status, _, _ = subscribe(website="http://spam.example")
    assert status == 202 and push_store.list_for("CAZ159", "es") == []


# --- limits and caps ----------------------------------------------------------------------------------------------

def test_per_ip_limit_is_5_per_hour():
    for i in range(5):
        assert subscribe(sub(f"https://fcm.googleapis.com/fcm/send/d{i}"), ip="9.9.9.9")[0] == 201
    status, body, headers = subscribe(sub("https://fcm.googleapis.com/fcm/send/d6"), ip="9.9.9.9")
    assert status == 429 and body["error"] == "rate_limited" and headers["Retry-After"] == "3600"
    assert subscribe(sub("https://fcm.googleapis.com/fcm/send/d7"), ip="8.8.8.8")[0] == 201  # another IP is fine


def test_per_endpoint_limit_is_10_per_day():
    s = sub()
    codes = [subscribe(s, ip=f"7.7.7.{i}")[0] for i in range(11)]
    assert codes[:10] == [201] * 10 and codes[10] == 429


def test_whole_app_limit_is_300_per_day(monkeypatch):
    monkeypatch.setattr("climateguard.push_signup.GLOBAL_PER_DAY", 3)
    codes = [subscribe(sub(f"https://fcm.googleapis.com/fcm/send/g{i}"), ip=f"6.6.6.{i}")[0] for i in range(4)]
    assert codes == [201, 201, 201, 503]


def test_total_subscriber_cap_is_500_and_existing_devices_keep_working(monkeypatch):
    monkeypatch.setattr(config, "MAX_PUSH_SUBSCRIBERS", 2)
    a, b, c = (sub(f"https://fcm.googleapis.com/fcm/send/{n}") for n in "abc")
    assert subscribe(a, ip="1.1.1.1")[0] == 201
    assert subscribe(b, ip="1.1.1.2")[0] == 201
    status, body, _ = subscribe(c, ip="1.1.1.3")
    assert (status, body["error"]) == (503, "subscriber_cap")
    assert subscribe(a, lang="vi", ip="1.1.1.4")[0] == 201  # a full house still lets a device change its language
    call("POST /push/unsubscribe", {"endpoint": "https://fcm.googleapis.com/fcm/send/b"})
    assert subscribe(c, ip="1.1.1.5")[0] == 201             # and a freed slot is reusable


def test_default_cap_is_500():
    assert config.MAX_PUSH_SUBSCRIBERS == 500


def test_limits_come_before_any_location_lookup(monkeypatch):
    calls = []
    monkeypatch.setattr(zones, "locate", lambda **kw: calls.append(kw) or dict(MN))
    for i in range(7):
        subscribe(sub(f"https://fcm.googleapis.com/fcm/send/x{i}"), ip="5.5.5.5")
    assert len(calls) == 5  # the 6th and 7th were refused before locating


def test_failed_setup_gives_the_slot_back(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("storage down")
    monkeypatch.setattr(push_store, "put", boom)
    assert subscribe()[0] == 503
    assert ratelimit.peek_counter("push-subscribers") == 0


# --- push-only zones are monitored ----------------------------------------------------------------------------------

def test_a_push_only_zone_becomes_monitored():
    assert "MNZ060" not in {z["zone"] for z in zones.monitored()}
    call("POST /push/subscribe", {"subscription": sub(), "lang": "en", "lat": 44.98, "lon": -93.27})
    assert "MNZ060" in {z["zone"] for z in zones.monitored()}


def test_hourly_recount_keeps_counting_push_subscribers():
    call("POST /push/subscribe", {"subscription": sub(), "lang": "en", "lat": 44.98, "lon": -93.27})
    subscriptions.refresh_confirmed(max_age_minutes=0)
    assert zones.get("MNZ060")["confirmed"] == 1
    call("POST /push/unsubscribe", {"endpoint": FCM})
    subscriptions.refresh_confirmed(max_age_minutes=0)
    assert zones.get("MNZ060")["confirmed"] == 0
    assert "MNZ060" not in {z["zone"] for z in zones.monitored()}


def test_expired_subscriptions_are_not_listed_or_counted(monkeypatch):
    import types
    import time as real_time

    subscribe()
    later = types.SimpleNamespace(time=lambda: real_time.time() + 400 * 86400)  # past the 365-day expiry
    monkeypatch.setattr(push_store, "time", later)
    assert push_store.list_for("CAZ159", "es") == [] and push_store.count_zone("CAZ159") == 0
    assert push_store.get_pointer(FCM) is None
