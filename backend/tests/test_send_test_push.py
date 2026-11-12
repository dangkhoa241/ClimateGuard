"""scripts/send_test_push.py against a fake push service: who gets the test notification, what it says in each
language, that the key comes from SSM and is never printed, and that nothing is deleted unless asked."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import pytest

import send_test_push as stp  # noqa: E402
from climateguard import config, push_store, ratelimit, ssm, webpush, zones  # noqa: E402
from climateguard.languages import LANGS  # noqa: E402

FAKE_KEY = "FAKEPRIVATEKEYMARKER1234567890abcdefghijklmnopq"
ROOT = Path(__file__).resolve().parents[2]


def device(n, zone="CAZ159", lang="es"):
    sub = {"endpoint": f"https://fcm.googleapis.com/fcm/send/dev{n}", "p256dh": "P" * 87, "auth": "A" * 22}
    push_store.put(zone, lang, sub)
    return sub


@pytest.fixture(autouse=True)
def local(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "LOCAL_DIR", tmp_path)
    monkeypatch.setattr(config, "STORAGE", "local")
    monkeypatch.setattr(config, "VAPID_PRIVATE_KEY", "")
    monkeypatch.setattr(config, "VAPID_PRIVATE_KEY_PARAM", "")
    monkeypatch.setattr(ratelimit, "_local", {})
    monkeypatch.setattr(ssm, "get_secret", lambda name: FAKE_KEY)
    monkeypatch.setattr(zones, "resolve_point", lambda lat, lon: {"zone": "MNZ060"})


@pytest.fixture
def service(monkeypatch):
    """The fake push service: records every request, answers 201 unless told otherwise."""
    calls, answers = [], {}

    def fake_send(sub, payload, key, contact=None):
        calls.append({"endpoint": sub["endpoint"], "payload": json.loads(payload), "key": key, "contact": contact})
        return answers.get(sub["endpoint"], 201)

    monkeypatch.setattr(webpush, "_send", fake_send)
    return calls, answers


def run(*argv):
    return stp.main(list(argv), storage="local")


def test_default_sends_only_to_the_most_recent_subscription(service, capsys):
    calls, _ = service
    for n in range(3):
        device(n)
    path = config.LOCAL_DIR / "push.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    for key, item in data.items():  # dev1 subscribed last
        if "endpoint" in item:
            item["created"] = {"dev0": 1000, "dev1": 3000, "dev2": 2000}[item["endpoint"][-4:]]
    path.write_text(json.dumps(data), encoding="utf-8")
    assert run() == 0
    assert [c["endpoint"][-4:] for c in calls] == ["dev1"]
    assert "Sent 1, gone 0, failed 0." in capsys.readouterr().out


def test_zip_sends_to_every_subscription_in_that_zone_only(service):
    calls, _ = service
    device(1, "CAZ159", "es"), device(2, "CAZ159", "vi"), device(3, "MNZ060", "en")
    assert run("--zip", "95202") == 0  # Stockton: the demo zone CAZ159, resolved without the network
    assert {c["endpoint"][-4:] for c in calls} == {"dev1", "dev2"}


def test_zip_lookup_registers_nothing(service):
    device(3, "MNZ060", "en")
    assert run("--zip", "55401") == 0  # Minneapolis -> resolve_point (faked) -> MNZ060
    assert not (config.LOCAL_DIR / "zones.json").exists()


@pytest.mark.parametrize("lang", list(LANGS))
def test_message_is_in_the_subscriptions_language_and_opens_its_alert_page(service, lang):
    calls, _ = service
    device(1, "CAZ159", lang)
    assert run("--open-url", "http://localhost:5173/") == 0
    p = calls[0]["payload"]
    assert p["title"] == "ClimateGuard" and p["body"] == stp.BODY[lang] and "ClimateGuard" in p["body"]
    assert p["url"] == f"http://localhost:5173/?zone=CAZ159&lang={lang}" and p["lang"] == lang
    assert set(stp.BODY) == set(LANGS)


def test_english_text_is_the_agreed_wording_and_default_link_is_the_live_app(service):
    calls, _ = service
    device(1, "CAZ159", "en")
    run()
    assert calls[0]["payload"]["body"] == "ClimateGuard test notification"
    assert calls[0]["payload"]["url"].startswith("https://climate-guard-khaki.vercel.app/?zone=CAZ159")
    assert calls[0]["contact"] == "https://climate-guard-khaki.vercel.app"


def test_key_is_read_from_ssm_at_runtime_and_never_printed(service, monkeypatch, capsys):
    calls, answers = service
    asked = []
    monkeypatch.setattr(ssm, "get_secret", lambda name: asked.append(name) or FAKE_KEY)
    a, b = device(1), device(2)
    answers[b["endpoint"]] = 500
    run("--zip", "95202")
    out = capsys.readouterr()
    assert asked == ["/climateguard/vapid-private-key"] and calls[0]["key"] == FAKE_KEY
    text = out.out + out.err
    assert FAKE_KEY not in text and "fcm.googleapis.com" not in text and a["p256dh"] not in text


def test_a_library_error_is_reported_without_its_text(service, monkeypatch, capsys):
    device(1)

    def boom(sub, payload, key, contact=None):
        raise RuntimeError(f"failed for {sub['endpoint']} with {key}")

    monkeypatch.setattr(webpush, "_send", boom)
    assert run() == 1
    text = capsys.readouterr().out
    assert "RuntimeError" in text and FAKE_KEY not in text and "fcm.googleapis.com" not in text


def test_missing_key_sends_nothing(service, monkeypatch, capsys):
    calls, _ = service
    device(1)

    def denied(name):
        raise RuntimeError("ParameterNotFound")

    monkeypatch.setattr(ssm, "get_secret", denied)
    monkeypatch.setattr(webpush, "_warned_no_key", False)
    assert run() == 1 and calls == []
    assert "Nothing was sent" in capsys.readouterr().out


def test_no_subscriptions_is_a_clear_message(service, capsys):
    calls, _ = service
    assert run() == 1 and run("--zip", "95202") == 1 and calls == []
    assert "No subscriptions found" in capsys.readouterr().out


def test_dry_run_lists_and_sends_nothing(service, capsys):
    calls, _ = service
    device(1, "CAZ159", "vi")
    assert run("--dry-run") == 0 and calls == []
    out = capsys.readouterr().out
    assert "zone CAZ159, language vi" in out and "nothing was sent" in out


@pytest.mark.parametrize("status", [404, 410])
def test_gone_devices_are_kept_unless_prune_is_passed(service, status):
    _, answers = service
    sub = device(1)
    ratelimit.claim_push_slot(500)
    answers[sub["endpoint"]] = status
    assert run() == 1
    assert len(push_store.list_for("CAZ159", "es")) == 1  # reported, not deleted
    assert run("--prune") == 1
    assert push_store.list_for("CAZ159", "es") == [] and push_store.get_pointer(sub["endpoint"]) is None
    assert ratelimit.peek_counter("push-subscribers") == 0


def test_real_runs_read_dynamodb_and_the_script_adds_no_api_route():
    import inspect

    assert inspect.signature(stp.main).parameters["storage"].default == "dynamodb"
    template = (ROOT / "template.yaml").read_text(encoding="utf-8")
    api = (ROOT / "backend/src/climateguard/handlers/api.py").read_text(encoding="utf-8")
    for text in (template, api):
        assert "push/test" not in text and "send_test_push" not in text
    assert "import boto3" not in (ROOT / "backend/scripts/send_test_push.py").read_text(encoding="utf-8")


def test_all_subscribers_skips_pointer_items():
    device(1), device(2, "MNZ060", "en")
    rows = push_store.all_subscribers()
    assert len(rows) == 2 and all("endpoint" in r for r in rows)
