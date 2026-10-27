"""Response cache with TTL. Storage follows config.STORAGE:
  local    -> one JSON file per key in backend/.local/cache/ (freshness from file mtime)
  dynamodb -> CACHE_TABLE (pk=key, body, expires_at). DynamoDB's TTL deletes
              expired items lazily, so freshness is also checked on read.
"""
import json
import time

from . import config

MAX_ITEM_BYTES = 350_000  # DynamoDB item limit is 400 KB


def _table():
    import boto3

    return boto3.resource("dynamodb").Table(config.CACHE_TABLE)


def get(key: str, ttl: int) -> dict | None:
    try:
        if config.STORAGE == "dynamodb":
            item = _table().get_item(Key={"key": key}).get("Item")
            if item and int(item["expires_at"]) > time.time():
                return json.loads(item["body"])
            return None
        path = config.CACHE_DIR / f"{key}.json"
        if path.exists() and time.time() - path.stat().st_mtime < ttl:
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:  # a cache miss is always safe
        print(f"cache read failed: {e}")
    return None


def put(key: str, value: dict, ttl: int) -> None:
    body = json.dumps(value, ensure_ascii=False)
    try:
        if config.STORAGE == "dynamodb":
            if len(body.encode()) <= MAX_ITEM_BYTES:
                _table().put_item(Item={"key": key, "body": body, "expires_at": int(time.time() + ttl)})
            return
        config.CACHE_DIR.mkdir(parents=True, exist_ok=True)
        (config.CACHE_DIR / f"{key}.json").write_text(body, encoding="utf-8")
    except Exception as e:
        print(f"cache write failed: {e}")
