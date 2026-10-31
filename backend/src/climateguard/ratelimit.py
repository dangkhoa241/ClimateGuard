"""Fixed-window counters and one-time markers for public endpoints.

dynamodb -> RATELIMIT_TABLE (pk "k", auto-expiring via `ttl`)
local    -> in-process dict (dev server / tests)
Identifiers (IPs, emails) are hashed before storage.
"""
import hashlib
import threading
import time
from decimal import Decimal

from . import config

_local: dict[str, tuple[float, float]] = {}  # key -> (count, expires_at)
_local_lock = threading.RLock()


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
        with _local_lock:
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
    with _local_lock:
        old = _local.get(key)
        if old and old[1] > time.time():
            return False
        _local[key] = (1, time.time() + keep_s)
        return True


def seen(name: str, ident: str) -> bool:
    key = f"once#{name}#{hashed(ident)}"
    if config.STORAGE == "dynamodb":
        return "Item" in _table().get_item(Key={"k": key}, ConsistentRead=True)
    with _local_lock:
        return _local.get(key, (0, 0))[1] > time.time()


def counter(name: str) -> int:
    """Increment and return a global counter (never expires)."""
    key = f"count#{name}"
    if config.STORAGE == "dynamodb":
        resp = _table().update_item(Key={"k": key}, UpdateExpression="ADD n :one",
                                    ExpressionAttributeValues={":one": 1}, ReturnValues="UPDATED_NEW")
        return int(resp["Attributes"]["n"])
    with _local_lock:
        n, exp = _local.get(key, (0, float("inf")))
        _local[key] = (n + 1, exp)
    return n + 1


def peek_counter(name: str) -> int:
    key = f"count#{name}"
    if config.STORAGE == "dynamodb":
        item = _table().get_item(Key={"k": key}, ConsistentRead=True).get("Item")
        return int(item["n"]) if item else 0
    with _local_lock:
        return int(_local.get(key, (0, 0))[0])


def claim_subscription(email: str, subscription_id: str, max_per_email: int, max_total: int,
                       keep_s: int = 365 * 86400) -> str:
    """Atomically register one distinct subscription and enforce per-email/global caps."""
    marker = f"once#subscription#{hashed(subscription_id)}"
    email_count = f"count#email-subscriptions#{hashed(email)}"
    total_count = "count#subscribers"
    now, expires = int(time.time()), int(time.time()) + keep_s
    if config.STORAGE == "dynamodb":
        from botocore.exceptions import ClientError

        # table.meta.client is a boto3 *resource* client: it serializes plain Python values to DynamoDB types
        # itself, so values here must NOT be pre-typed ({"N": "1"}), or they are stored/compared as maps.
        values = {":zero": 0, ":one": 1}

        def update(key: str, maximum: int, with_ttl: bool) -> dict:
            result = {
                "TableName": config.RATELIMIT_TABLE,
                "Key": {"k": key},
                "UpdateExpression": "SET #n = if_not_exists(#n, :zero) + :one"
                                  + (", #ttl = :ttl" if with_ttl else ""),
                "ConditionExpression": "attribute_not_exists(#n) OR #n < :maximum",
                "ExpressionAttributeNames": {"#n": "n", **({"#ttl": "ttl"} if with_ttl else {})},
                "ExpressionAttributeValues": {**values, ":maximum": maximum},
            }
            if with_ttl:
                result["ExpressionAttributeValues"][":ttl"] = expires
            return result

        try:
            _table().meta.client.transact_write_items(TransactItems=[
                {"Put": {"TableName": config.RATELIMIT_TABLE,
                         "Item": {"k": marker, "ttl": expires},
                         "ConditionExpression": "attribute_not_exists(k)"}},
                {"Update": update(email_count, max_per_email, True)},
                {"Update": update(total_count, max_total, False)},
            ])
            return "created"
        except ClientError as e:
            if e.response["Error"]["Code"] != "TransactionCanceledException":
                raise
            if seen("subscription", subscription_id):
                return "existing"
            if peek_counter(f"email-subscriptions#{hashed(email)}") >= max_per_email:
                return "email_subscription_cap"
            if peek_counter("subscribers") >= max_total:
                return "subscriber_cap"
            raise

    with _local_lock:
        marker_rec = _local.get(marker)
        if marker_rec and marker_rec[1] > now:
            return "existing"
        email_rec = _local.get(email_count, (0, 0))
        total_rec = _local.get(total_count, (0, float("inf")))
        if email_rec[1] > now and email_rec[0] >= max_per_email:
            return "email_subscription_cap"
        if total_rec[0] >= max_total:
            return "subscriber_cap"
        _local[marker] = (1, expires)
        _local[email_count] = ((email_rec[0] if email_rec[1] > now else 0) + 1, expires)
        _local[total_count] = (total_rec[0] + 1, total_rec[1])
        return "created"


def release_subscription(email: str, subscription_id: str) -> None:
    """Undo a newly claimed subscription if delivery setup fails."""
    marker = f"once#subscription#{hashed(subscription_id)}"
    email_count = f"count#email-subscriptions#{hashed(email)}"
    total_count = "count#subscribers"
    if config.STORAGE == "dynamodb":
        _table().meta.client.transact_write_items(TransactItems=[
            {"Delete": {"TableName": config.RATELIMIT_TABLE, "Key": {"k": marker},
                        "ConditionExpression": "attribute_exists(k)"}},
            {"Update": {"TableName": config.RATELIMIT_TABLE, "Key": {"k": email_count},
                        "UpdateExpression": "ADD #n :minus",
                        "ConditionExpression": "#n >= :one",
                        "ExpressionAttributeNames": {"#n": "n"},
                        "ExpressionAttributeValues": {":minus": -1, ":one": 1}}},
            {"Update": {"TableName": config.RATELIMIT_TABLE, "Key": {"k": total_count},
                        "UpdateExpression": "ADD #n :minus",
                        "ConditionExpression": "#n >= :one",
                        "ExpressionAttributeNames": {"#n": "n"},
                        "ExpressionAttributeValues": {":minus": -1, ":one": 1}}},
        ])
        return
    with _local_lock:
        if marker not in _local:
            return
        del _local[marker]
        for key in (email_count, total_count):
            count, expires = _local.get(key, (0, 0))
            if count > 1:
                _local[key] = (count - 1, expires)
            else:
                _local.pop(key, None)


def spend_value(day: str) -> float | None:
    key = f"spend#{day}"
    if config.STORAGE == "dynamodb":
        item = _table().get_item(Key={"k": key}, ConsistentRead=True).get("Item")
        return float(item["spend_usd"]) if item else None
    with _local_lock:
        record = _local.get(key)
        return record[0] if record and record[1] > time.time() else None


def initialize_spend(day: str, amount: float, keep_s: int = 3 * 86400) -> None:
    """Seed today's counter from usage recorded before the counter was first used."""
    key, expires = f"spend#{day}", int(time.time()) + keep_s
    if config.STORAGE == "dynamodb":
        from botocore.exceptions import ClientError

        try:
            _table().put_item(Item={"k": key, "spend_usd": Decimal(str(amount)), "ttl": expires},
                              ConditionExpression="attribute_not_exists(k)")
        except ClientError as e:
            if e.response["Error"]["Code"] != "ConditionalCheckFailedException":
                raise
        return
    with _local_lock:
        old = _local.get(key)
        if not old or old[1] <= time.time():
            _local[key] = (amount, expires)


def reserve_spend(day: str, amount: float, cap: float, keep_s: int = 3 * 86400) -> bool:
    """Atomically reserve estimated model spend without crossing the daily cap."""
    key, expires = f"spend#{day}", int(time.time()) + keep_s
    if config.STORAGE == "dynamodb":
        from botocore.exceptions import ClientError

        remaining = Decimal(str(cap)) - Decimal(str(amount))
        try:
            _table().update_item(
                Key={"k": key},
                UpdateExpression="ADD spend_usd :amount SET #ttl = if_not_exists(#ttl, :ttl)",
                ConditionExpression="attribute_exists(spend_usd) AND spend_usd <= :remaining",
                ExpressionAttributeNames={"#ttl": "ttl"},
                ExpressionAttributeValues={":amount": Decimal(str(amount)), ":remaining": remaining,
                                           ":ttl": expires},
            )
            return True
        except ClientError as e:
            if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                return False
            raise
    with _local_lock:
        used, old_exp = _local.get(key, (0.0, expires))
        if old_exp <= time.time():
            used = 0.0
        if used + amount > cap + 1e-12:
            return False
        _local[key] = (used + amount, old_exp if old_exp > time.time() else expires)
        return True


def adjust_spend(day: str, amount: float) -> None:
    """Reconcile a reservation with the provider's reported cost."""
    key = f"spend#{day}"
    if config.STORAGE == "dynamodb":
        _table().update_item(Key={"k": key}, UpdateExpression="ADD spend_usd :amount",
                            ExpressionAttributeValues={":amount": Decimal(str(amount))})
        return
    with _local_lock:
        used, expires = _local.get(key, (0.0, time.time() + 3 * 86400))
        _local[key] = (max(0.0, used + amount), expires)
