"""Daily model budget (DAILY_MODEL_BUDGET_USD, default $5, UTC day).

Over budget, the monitoring agent only runs for zones with an active NWS *Warning*;
everything else is logged as skipped. Spend comes from the usage log (estimated cost
per call, cache hits are free).
"""
import json
import time
from datetime import datetime, timezone
from decimal import Decimal

from . import config


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def spent_today_usd() -> float:
    day = _today()
    if config.STORAGE == "dynamodb":
        import boto3
        from boto3.dynamodb.conditions import Key

        table, total, kwargs = boto3.resource("dynamodb").Table(config.USAGE_TABLE), 0.0, {}
        while True:
            page = table.query(KeyConditionExpression=Key("day").eq(day), ProjectionExpression="cost_usd", **kwargs)
            total += sum(float(i.get("cost_usd", Decimal(0))) for i in page["Items"])
            if "LastEvaluatedKey" not in page:
                return total
            kwargs["ExclusiveStartKey"] = page["LastEvaluatedKey"]
    if not config.USAGE_LOG.exists():
        return 0.0
    start = datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp()
    total = 0.0
    for line in config.USAGE_LOG.read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            if start <= r["ts"] <= time.time():
                total += r.get("cost_usd", 0.0)
    return total


def over_budget() -> bool:
    return spent_today_usd() >= config.DAILY_MODEL_BUDGET_USD


def has_active_warning(snapshot: dict) -> bool:
    return any(a["event"].endswith("Warning") for a in snapshot.get("alerts", []))
