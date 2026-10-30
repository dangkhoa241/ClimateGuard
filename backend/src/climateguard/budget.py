"""UTC daily model-spend cap, reserved atomically before a model request."""
import json
import math
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

from . import config, ratelimit, usage

BUSY_MESSAGE = "The demo is busy, please try again later"


class SpendCapExceeded(Exception):
    """The estimated cost of a new model call would exceed today's spend cap."""


@dataclass(frozen=True)
class Reservation:
    day: str
    amount: float


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def spent_today_usd() -> float:
    """Actual estimated costs from the usage log (for the demo's public cost display)."""
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
            record = json.loads(line)
            if start <= record["ts"] <= time.time():
                total += record.get("cost_usd", 0.0)
    return total


def _current_spend(day: str) -> float:
    value = ratelimit.spend_value(day)
    if value is None:
        ratelimit.initialize_spend(day, spent_today_usd())
        value = ratelimit.spend_value(day)
    if value is None:
        raise RuntimeError("daily model spend counter could not be initialized")
    return value


def over_budget() -> bool:
    return _current_spend(_today()) >= config.DAILY_MODEL_BUDGET_USD


def _estimate_tokens(value) -> tuple[str, int]:
    if isinstance(value, str):
        return ("", 1) if value.startswith("data:image/") else (value, 0)
    if isinstance(value, dict):
        if value.get("type") in ("image_url", "input_image"):
            return "", 1
        parts = [_estimate_tokens(item) for pair in value.items() for item in pair]
    elif isinstance(value, (list, tuple)):
        parts = [_estimate_tokens(item) for item in value]
    else:
        return str(value), 0
    return " ".join(text for text, _ in parts), sum(images for _, images in parts)


def estimate_call_usd(model: str, payload, max_output_tokens: int, extra_usd: float = 0.0) -> float:
    """Conservative token estimate; image payloads use a fixed 2,048-token allowance each."""
    text, images = _estimate_tokens(payload)
    input_tokens = math.ceil(len(text.encode("utf-8")) / 3) + images * 2048
    return usage.estimate_cost(model, input_tokens, max_output_tokens) + extra_usd


def reserve(estimated_usd: float) -> Reservation:
    if estimated_usd < 0:
        raise ValueError("estimated model cost cannot be negative")
    day = _today()
    if estimated_usd:
        _current_spend(day)
    if estimated_usd and not ratelimit.reserve_spend(day, estimated_usd, config.DAILY_MODEL_BUDGET_USD):
        raise SpendCapExceeded(BUSY_MESSAGE)
    return Reservation(day, estimated_usd)


def reserve_call(model: str, payload, max_output_tokens: int, extra_usd: float = 0.0) -> Reservation:
    return reserve(estimate_call_usd(model, payload, max_output_tokens, extra_usd))


def settle(reservation: Reservation, actual_usd: float) -> None:
    """Replace the conservative reservation with reported usage while retaining the same UTC day."""
    if actual_usd < 0:
        raise ValueError("actual model cost cannot be negative")
    delta = actual_usd - reservation.amount
    if delta:
        ratelimit.adjust_spend(reservation.day, delta)
