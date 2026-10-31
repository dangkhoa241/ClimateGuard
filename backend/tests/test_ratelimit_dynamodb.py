"""The DynamoDB sign-up claim, checked on the wire.

The first live sign-up failed with `ValidationException: Invalid ConditionExpression ... operator: <, operand type: M`
because the code passed pre-typed values ({"N": "3"}) to a boto3 *resource* client, which serializes values itself and
turned them into maps. A fake client can't catch that, so these tests let boto3's real resource client build the request
(offline, with dummy credentials) and read the JSON it would have sent to DynamoDB.
"""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import boto3
import pytest

from climateguard import config, ratelimit


@pytest.fixture
def sent(monkeypatch):
    """The request bodies the resource client would send, per operation (nothing leaves the machine)."""
    monkeypatch.setattr(config, "STORAGE", "dynamodb")
    monkeypatch.setattr(config, "RATELIMIT_TABLE", "limits")
    resource = boto3.resource("dynamodb", region_name="us-east-2", aws_access_key_id="test", aws_secret_access_key="test")
    bodies = []

    def capture(params, **kwargs):
        bodies.append(json.loads(params["body"]))
        return SimpleNamespace(status_code=200, headers={}, content=b"{}"), {}

    resource.meta.client.meta.events.register("before-call.dynamodb.TransactWriteItems", capture)
    monkeypatch.setattr(ratelimit, "_table", lambda: resource.Table("limits"))
    return bodies


def _types(node):
    """Every DynamoDB type tag used in a request body."""
    if isinstance(node, dict):
        found = {k for k in node if k in ("S", "N", "M", "L", "BOOL", "NULL")}
        return found.union(*(_types(v) for v in node.values())) if node else found
    if isinstance(node, list):
        return set().union(*(_types(v) for v in node)) if node else set()
    return set()


def test_claim_sends_numbers_and_strings_not_maps(sent):
    assert ratelimit.claim_subscription("maria@example.com", "maria@example.com|CAZ159|es", 3, 500) == "created"
    [body] = sent
    put, email_count, total_count = body["TransactItems"]
    assert put["Put"]["Item"]["k"] == {"S": f"once#subscription#{ratelimit.hashed('maria@example.com|CAZ159|es')}"}
    assert put["Put"]["Item"]["ttl"]["N"].isdigit()
    assert email_count["Update"]["ExpressionAttributeValues"][":maximum"] == {"N": "3"}
    assert email_count["Update"]["ExpressionAttributeValues"][":zero"] == {"N": "0"}
    assert email_count["Update"]["ExpressionAttributeValues"][":ttl"]["N"].isdigit()
    assert total_count["Update"]["ExpressionAttributeValues"][":maximum"] == {"N": "500"}
    assert email_count["Update"]["Key"]["k"]["S"].startswith("count#email-subscriptions#")
    assert "M" not in _types(body)  # the production bug: a value sent as a map


def test_release_sends_numbers_and_strings_not_maps(sent):
    ratelimit.release_subscription("maria@example.com", "maria@example.com|CAZ159|es")
    [body] = sent
    delete, email_count, total_count = body["TransactItems"]
    assert delete["Delete"]["Key"]["k"]["S"].startswith("once#subscription#")
    for update in (email_count, total_count):
        assert update["Update"]["ExpressionAttributeValues"] == {":minus": {"N": "-1"}, ":one": {"N": "1"}}
    assert "M" not in _types(body)
