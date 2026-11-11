"""Web push subscriptions: validation and storage.

One subscription per device (browser endpoint), for one zone and one language.
Storage follows config.STORAGE:
  dynamodb -> PUSH_TABLE (pk "zone", sk), auto-expiring via `ttl`
  local    -> JSON file backend/.local/push.json (dev and tests)
Items (no secondary index, so no extra capacity):
  subscriber: zone=<NWS zone>, sk="<lang>#<endpoint hash>"  -> endpoint, p256dh, auth, lang
  pointer:    zone="EP#<endpoint hash>", sk="ptr"           -> zone, lang  (how unsubscribe finds the subscriber
              from nothing but the endpoint, which is the only secret the device has)
The endpoint URL is a capability: whoever holds it can push to that device, so it is never logged or returned.
"""
import base64
import hashlib
import json
import re
import time
from urllib.parse import urlsplit

from . import config

KEEP_S = 365 * 86400
MAX_ENDPOINT_CHARS = 600

# The real push services. The backend POSTs to whatever endpoint a device registers, so the host must be one of
# these (an exact match, or a subdomain of one: "." + name), never a lookalike. Checked on a parsed URL.
ALLOWED_HOSTS = (
    "fcm.googleapis.com",                 # Chrome, Edge, Brave, Android browsers
    "updates.push.services.mozilla.com",  # Firefox
    "push.apple.com",                     # Safari and installed iPhone apps (web.push.apple.com and others)
    "notify.windows.com",                 # Edge on Windows (wns2-xxx.notify.windows.com)
)
_BAD_CHARS = re.compile(r"[\x00-\x20\x7f\\]")


class PushError(Exception):
    def __init__(self, code: str, status: int = 400):
        super().__init__(code)
        self.code, self.status = code, status


def _b64_len(value, expected: int, first_byte: int | None = None) -> bool:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]+={0,2}", value):
        return False
    try:
        raw = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except Exception:
        return False
    return len(raw) == expected and (first_byte is None or raw[0] == first_byte)


def host_allowed(host: str) -> bool:
    return any(host == name or host.endswith("." + name) for name in ALLOWED_HOSTS)


def validate_endpoint(endpoint) -> str:
    if not isinstance(endpoint, str) or not endpoint or len(endpoint) > MAX_ENDPOINT_CHARS or _BAD_CHARS.search(endpoint):
        raise PushError("invalid_subscription")
    try:
        parts = urlsplit(endpoint)
        host, port = parts.hostname, parts.port
    except ValueError:
        raise PushError("invalid_subscription") from None
    if (parts.scheme != "https" or not host or parts.username is not None or parts.password is not None
            or port is not None or parts.fragment or not host.isascii() or host.endswith(".")
            or not host_allowed(host)):
        raise PushError("invalid_subscription")
    return endpoint


def validate_subscription(sub) -> dict:
    """A browser PushSubscription.toJSON(): {endpoint, keys: {p256dh, auth}} -> clean dict, or PushError."""
    if not isinstance(sub, dict) or not isinstance(sub.get("keys"), dict):
        raise PushError("invalid_subscription")
    endpoint = validate_endpoint(sub.get("endpoint"))
    p256dh, auth = sub["keys"].get("p256dh"), sub["keys"].get("auth")
    if not _b64_len(p256dh, 65, 0x04) or not _b64_len(auth, 16):
        raise PushError("invalid_subscription")
    return {"endpoint": endpoint, "p256dh": p256dh.rstrip("="), "auth": auth.rstrip("=")}


def endpoint_hash(endpoint: str) -> str:
    return hashlib.sha256(f"climateguard-push:{endpoint}".encode()).hexdigest()[:24]


# --- storage ---------------------------------------------------------------------------------------------------

def _table():
    import boto3

    return boto3.resource("dynamodb").Table(config.PUSH_TABLE)


def _local_path():
    return config.LOCAL_DIR / "push.json"


def _load() -> dict:
    p = _local_path()
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def _save(data: dict) -> None:
    _local_path().parent.mkdir(parents=True, exist_ok=True)
    _local_path().write_text(json.dumps(data), encoding="utf-8")


def _live(item: dict) -> bool:
    return int(item.get("ttl", 0)) > time.time()  # DynamoDB TTL deletes lazily; never send to an expired one


def get_pointer(endpoint: str) -> dict | None:
    h = endpoint_hash(endpoint)
    if config.STORAGE == "dynamodb":
        item = _table().get_item(Key={"zone": f"EP#{h}", "sk": "ptr"}).get("Item")
    else:
        item = _load().get(f"EP#{h}|ptr")
    return item if item and _live(item) else None


def put(zone: str, lang: str, sub: dict) -> None:
    """Store (or refresh) a subscription and its pointer together."""
    h, ttl = endpoint_hash(sub["endpoint"]), int(time.time()) + KEEP_S
    record = {"zone": zone, "sk": f"{lang}#{h}", "lang": lang, "endpoint": sub["endpoint"], "p256dh": sub["p256dh"],
              "auth": sub["auth"], "created": int(time.time()), "ttl": ttl}
    pointer = {"zone": f"EP#{h}", "sk": "ptr", "target_zone": zone, "lang": lang, "ttl": ttl}
    if config.STORAGE == "dynamodb":
        _table().meta.client.transact_write_items(TransactItems=[
            {"Put": {"TableName": config.PUSH_TABLE, "Item": record}},
            {"Put": {"TableName": config.PUSH_TABLE, "Item": pointer}},
        ])
        return
    data = _load()
    data[f"{zone}|{lang}#{h}"] = record
    data[f"EP#{h}|ptr"] = pointer
    _save(data)


def delete(endpoint: str) -> dict | None:
    """Remove a device's subscription (and pointer). Returns the removed pointer, or None if it had none."""
    ptr = get_pointer(endpoint)
    h = endpoint_hash(endpoint)
    if config.STORAGE == "dynamodb":
        items = [{"Delete": {"TableName": config.PUSH_TABLE, "Key": {"zone": f"EP#{h}", "sk": "ptr"}}}]
        if ptr:
            items.append({"Delete": {"TableName": config.PUSH_TABLE,
                                     "Key": {"zone": ptr["target_zone"], "sk": f"{ptr['lang']}#{h}"}}})
        _table().meta.client.transact_write_items(TransactItems=items)
        return ptr
    data = _load()
    data.pop(f"EP#{h}|ptr", None)
    if ptr:
        data.pop(f"{ptr['target_zone']}|{ptr['lang']}#{h}", None)
    _save(data)
    return ptr


def delete_subscriber(zone: str, lang: str, h: str) -> None:
    """Remove one stored subscriber by key (the push service said the device is gone)."""
    if config.STORAGE == "dynamodb":
        _table().meta.client.transact_write_items(TransactItems=[
            {"Delete": {"TableName": config.PUSH_TABLE, "Key": {"zone": zone, "sk": f"{lang}#{h}"}}},
            {"Delete": {"TableName": config.PUSH_TABLE, "Key": {"zone": f"EP#{h}", "sk": "ptr"}}},
        ])
        return
    data = _load()
    data.pop(f"{zone}|{lang}#{h}", None)
    data.pop(f"EP#{h}|ptr", None)
    _save(data)


def list_for(zone: str, lang: str) -> list[dict]:
    if config.STORAGE == "dynamodb":
        from boto3.dynamodb.conditions import Key

        out, kwargs = [], {"KeyConditionExpression": Key("zone").eq(zone) & Key("sk").begins_with(f"{lang}#")}
        while True:
            page = _table().query(**kwargs)
            out += page["Items"]
            if "LastEvaluatedKey" not in page:
                break
            kwargs["ExclusiveStartKey"] = page["LastEvaluatedKey"]
    else:
        out = [v for k, v in _load().items() if k.startswith(f"{zone}|{lang}#")]
    return [i for i in out if _live(i)]


def count_zone(zone: str) -> int:
    if config.STORAGE == "dynamodb":
        from boto3.dynamodb.conditions import Attr, Key

        total, kwargs = 0, {"KeyConditionExpression": Key("zone").eq(zone), "Select": "COUNT",
                            "FilterExpression": Attr("ttl").gt(int(time.time()))}
        while True:
            page = _table().query(**kwargs)
            total += page["Count"]
            if "LastEvaluatedKey" not in page:
                return total
            kwargs["ExclusiveStartKey"] = page["LastEvaluatedKey"]
    return sum(1 for k, v in _load().items() if k.startswith(f"{zone}|") and _live(v))
