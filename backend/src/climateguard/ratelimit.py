"""Fixed-window counters and one-time markers for public endpoints.

dynamodb -> RATELIMIT_TABLE (pk "k", auto-expiring via `ttl`)
local    -> in-process dict (dev server / tests)
Identifiers (IPs, emails) are hashed before storage.
"""
import hashlib
import time

from . import config

_local: dict[str, tuple[int, float]] = {}  # key -> (count, expires_at)


def _table():
    import boto3

    return boto3.resource("dynamodb").Table(config.RATELIMIT_TABLE)


def hashed(value: str) -> str:
    return hashlib.sha256(f"climateguard:{value.strip().lower()}".encode()).hexdigest()[:24]


def hit(name: str, ident: str, limit: int, window_s: int) -> bool:
    """Count one request for (name, ident) in the current window. True if still within `limit`."""
    window = int(time.time() // window_s)
    key = f"rl#{name}#{hashed(ident)}#{window}"
    expires = (window + 1) * window_s + 60
    if config.STORAGE == "dynamodb":
        resp = _table().update_item(
            Key={"k": key},
            UpdateExpression="ADD n :one SET #t = if_not_exists(#t, :ttl)",
            ExpressionAttributeNames={"#t": "ttl"},
            ExpressionAttributeValues={":one": 1, ":ttl": expires},
            ReturnValues="UPDATED_NEW",
        )
        count = int(resp["Attributes"]["n"])
    else:
        n, exp = _local.get(key, (0, expires))
        count = n + 1
        _local[key] = (count, exp)
    return count <= limit


def mark_once(name: str, ident: str, keep_s: int = 365 * 86400) -> bool:
    """Record `ident` under `name`. True the first time, False if already recorded."""
    key = f"once#{name}#{hashed(ident)}"
    if config.STORAGE == "dynamodb":
        from botocore.exceptions import ClientError

        try:
            _table().put_item(Item={"k": key, "ttl": int(time.time()) + keep_s},
                              ConditionExpression="attribute_not_exists(k)")
            return True
        except ClientError as e:
            if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                return False
            raise
    if key in _local:
        return False
    _local[key] = (1, time.time() + keep_s)
    return True


def seen(name: str, ident: str) -> bool:
    key = f"once#{name}#{hashed(ident)}"
    if config.STORAGE == "dynamodb":
        return "Item" in _table().get_item(Key={"k": key})
    return key in _local


def counter(name: str) -> int:
    """Increment and return a global counter (never expires)."""
    key = f"count#{name}"
    if config.STORAGE == "dynamodb":
        resp = _table().update_item(Key={"k": key}, UpdateExpression="ADD n :one",
                                    ExpressionAttributeValues={":one": 1}, ReturnValues="UPDATED_NEW")
        return int(resp["Attributes"]["n"])
    n, exp = _local.get(key, (0, float("inf")))
    _local[key] = (n + 1, exp)
    return n + 1


def peek_counter(name: str) -> int:
    key = f"count#{name}"
    if config.STORAGE == "dynamodb":
        item = _table().get_item(Key={"k": key}).get("Item")
        return int(item["n"]) if item else 0
    return _local.get(key, (0, 0))[0]
