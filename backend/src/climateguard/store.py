"""Snapshot storage: local JSON files (dev) or DynamoDB (Lambda), picked by config.STORAGE.

DynamoDB layout (table SNAPSHOTS_TABLE, pk=zone, sk):
  sk="latest"             current snapshot (overwritten every run)
  sk="hist#<iso time>"    history copy, only when the fingerprint changed; auto-deleted after 7 days
The snapshot body is stored as a JSON string to avoid float/Decimal conversion.
"""
import json
import time

from . import config

HISTORY_DAYS = 7


class LocalStore:
    def __init__(self):
        self.dir = config.LOCAL_DIR / "snapshots"

    def put_snapshot(self, snap: dict, changed: bool = True) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        (self.dir / f"{snap['zone']}.json").write_text(json.dumps(snap, indent=1, ensure_ascii=False),
                                                       encoding="utf-8")

    def get_latest(self, zone: str) -> dict | None:
        path = self.dir / f"{zone.upper()}.json"
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


class DynamoStore:
    def __init__(self):
        import boto3  # available in the Lambda runtime; dev-only dependency locally

        self.table = boto3.resource("dynamodb").Table(config.SNAPSHOTS_TABLE)

    def put_snapshot(self, snap: dict, changed: bool = True) -> None:
        body = json.dumps(snap, ensure_ascii=False)
        base = {"zone": snap["zone"], "fingerprint": snap["fingerprint"],
                "generated_at": snap["generated_at"], "body": body}
        self.table.put_item(Item={**base, "sk": "latest"})
        if changed:  # unchanged runs would only duplicate history (and write capacity)
            self.table.put_item(Item={**base, "sk": f"hist#{snap['generated_at']}",
                                      "ttl": int(time.time()) + HISTORY_DAYS * 86400})

    def get_latest(self, zone: str) -> dict | None:
        item = self.table.get_item(Key={"zone": zone.upper(), "sk": "latest"}).get("Item")
        return json.loads(item["body"]) if item else None


def get_store():
    return DynamoStore() if config.STORAGE == "dynamodb" else LocalStore()
