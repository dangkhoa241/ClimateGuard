"""Snapshot storage: local JSON files (dev) or DynamoDB (Lambda), picked by config.STORAGE.

DynamoDB layout (table SNAPSHOTS_TABLE, pk=city, sk):
  sk="latest"             current snapshot
  sk="hist#<iso time>"    history copy, auto-deleted after 7 days via `ttl`
The snapshot body is stored as a JSON string to avoid float/Decimal conversion.
"""
import json
import time

from . import config

HISTORY_DAYS = 7


class LocalStore:
    def __init__(self):
        self.dir = config.LOCAL_DIR / "snapshots"

    def put_snapshot(self, snap: dict) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        (self.dir / f"{snap['city']}.json").write_text(json.dumps(snap, indent=1, ensure_ascii=False),
                                                       encoding="utf-8")

    def get_latest(self, city: str) -> dict | None:
        path = self.dir / f"{city}.json"
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


class DynamoStore:
    def __init__(self):
        import boto3  # available in the Lambda runtime; dev-only dependency locally

        self.table = boto3.resource("dynamodb").Table(config.SNAPSHOTS_TABLE)

    def put_snapshot(self, snap: dict) -> None:
        body = json.dumps(snap, ensure_ascii=False)
        base = {"city": snap["city"], "fingerprint": snap["fingerprint"],
                "generated_at": snap["generated_at"], "body": body}
        self.table.put_item(Item={**base, "sk": "latest"})
        self.table.put_item(Item={**base, "sk": f"hist#{snap['generated_at']}",
                                  "ttl": int(time.time()) + HISTORY_DAYS * 86400})

    def get_latest(self, city: str) -> dict | None:
        item = self.table.get_item(Key={"city": city, "sk": "latest"}).get("Item")
        return json.loads(item["body"]) if item else None


def get_store():
    return DynamoStore() if config.STORAGE == "dynamodb" else LocalStore()
