"""Sent alerts and the monitoring agent's decision log. Storage follows config.STORAGE:
  local    -> JSON lines in backend/.local/alerts/<zone>.jsonl
  dynamodb -> ALERTS_TABLE (pk=zone, sk="sent#<iso>" | "decision#<iso>", auto-expiring via `ttl`)
"""
import json
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from . import config

KEEP_DAYS = {"sent": 14, "decision": 30}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _table():
    import boto3

    return boto3.resource("dynamodb").Table(config.ALERTS_TABLE)


def _local_path(zone: str):
    return config.LOCAL_DIR / "alerts" / f"{zone}.jsonl"


def _put(zone: str, kind: str, record: dict) -> dict:
    ts = _now().isoformat(timespec="seconds")
    item = {"zone": zone, "sk": f"{kind}#{ts}", "kind": kind, "ts": ts, **record}
    if config.STORAGE == "dynamodb":
        body = json.dumps(item, ensure_ascii=False)
        _table().put_item(Item={"zone": zone, "sk": item["sk"], "kind": kind, "ts": ts, "body": body,
                                "ttl": int(time.time()) + KEEP_DAYS[kind] * 86400})
    else:
        path = _local_path(zone)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
    return item


def _since(zone: str, kind: str, hours: float) -> list[dict]:
    cutoff = (_now() - timedelta(hours=hours)).isoformat(timespec="seconds")
    if config.STORAGE == "dynamodb":
        from boto3.dynamodb.conditions import Key

        resp = _table().query(KeyConditionExpression=Key("zone").eq(zone)
                              & Key("sk").between(f"{kind}#{cutoff}", f"{kind}#~"))
        return [json.loads(i["body"]) for i in resp["Items"]]
    path = _local_path(zone)
    if not path.exists():
        return []
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return [r for r in rows if r["kind"] == kind and r["ts"] >= cutoff]


def record_sent(zone: str, hazard: str, severity: str, messages: dict, reason: str) -> dict:
    return _put(zone, "sent", {"hazard": hazard, "severity": severity, "messages": messages, "reason": reason})


def recent_sent(zone: str, hours: float = 48) -> list[dict]:
    return _since(zone, "sent", hours)


def log_decision(zone: str, action: str, reason: str, **details) -> dict:
    """action: 'sent' | 'skipped' | 'error'. One entry per monitoring run."""
    details = {k: (float(v) if isinstance(v, Decimal) else v) for k, v in details.items()}
    return _put(zone, "decision", {"action": action, "reason": reason, **details})


def recent_decisions(zone: str, hours: float = 48) -> list[dict]:
    return _since(zone, "decision", hours)


def clear_local(zone: str) -> None:
    """Dev/demo helper: forget local alerts for a zone."""
    _local_path(zone).unlink(missing_ok=True)
