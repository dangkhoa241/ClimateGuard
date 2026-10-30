"""Offline tests for atomic model-spend reservations and daily-cap estimates."""
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest

from climateguard import budget, config, ratelimit


@pytest.fixture
def local_budget(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "STORAGE", "local")
    monkeypatch.setattr(config, "LOCAL_DIR", tmp_path)
    monkeypatch.setattr(config, "USAGE_LOG", tmp_path / "usage.jsonl")
    monkeypatch.setattr(config, "DAILY_MODEL_BUDGET_USD", 1.0)
    monkeypatch.setattr(ratelimit, "_local", {})


def test_reservations_cannot_cross_daily_cap(local_budget):
    reservation = budget.reserve(0.7)
    budget.settle(reservation, 0.25)
    second = budget.reserve(0.7)
    with pytest.raises(budget.SpendCapExceeded, match="busy"):
        budget.reserve(0.1)
    budget.settle(second, 0.7)
    assert budget.over_budget() is False


def test_image_payload_estimate_does_not_count_base64_as_text():
    payload = [{"role": "user", "content": [
        {"type": "text", "text": "Describe this photo."},
        {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + "A" * 100_000}},
    ]}]
    assert budget.estimate_call_usd("muse-spark-1.3", payload, 500) < 0.01


def test_token_estimate_accounts_for_multibyte_text():
    english = [{"role": "user", "content": "a" * 30}]
    chinese = [{"role": "user", "content": "你" * 30}]
    assert budget.estimate_call_usd("muse-spark-1.3", chinese, 0) > \
        budget.estimate_call_usd("muse-spark-1.3", english, 0)


def test_dynamodb_subscription_claim_is_one_transaction(monkeypatch):
    monkeypatch.setattr(config, "STORAGE", "dynamodb")
    monkeypatch.setattr(config, "RATELIMIT_TABLE", "limits")
    client = SimpleNamespace(transact_write_items=lambda **kwargs: calls.append(kwargs))
    calls = []
    table = SimpleNamespace(meta=SimpleNamespace(client=client))
    monkeypatch.setattr(ratelimit, "_table", lambda: table)

    assert ratelimit.claim_subscription("maria@example.com", "maria@example.com|CAZ159|es", 3, 500) == "created"
    [transaction] = calls
    assert len(transaction["TransactItems"]) == 3
    marker, email_count, total_count = transaction["TransactItems"]
    assert marker["Put"]["ConditionExpression"] == "attribute_not_exists(k)"
    assert email_count["Update"]["ConditionExpression"] == "attribute_not_exists(#n) OR #n < :maximum"
    assert "ttl" in email_count["Update"]["ExpressionAttributeNames"].values()
    assert "ttl" not in total_count["Update"]["ExpressionAttributeNames"].values()


def test_dynamodb_spend_reservation_is_conditioned_on_remaining_budget(monkeypatch):
    monkeypatch.setattr(config, "STORAGE", "dynamodb")
    updates = []
    table = SimpleNamespace(update_item=lambda **kwargs: updates.append(kwargs))
    monkeypatch.setattr(ratelimit, "_table", lambda: table)

    assert ratelimit.reserve_spend("2026-01-01", 0.25, 3.0)
    [update] = updates
    assert update["ConditionExpression"] == "attribute_exists(spend_usd) AND spend_usd <= :remaining"
    assert float(update["ExpressionAttributeValues"][":remaining"]) == 2.75
