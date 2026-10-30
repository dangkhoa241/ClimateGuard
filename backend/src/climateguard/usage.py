"""Log every model call with token counts and estimated cost.

Storage follows config.STORAGE:
  local    -> JSON lines in backend/.local/usage.jsonl
  dynamodb -> USAGE_TABLE (pk=day "YYYY-MM-DD", sk="<epoch>#<uuid>")
"""
import json
import math
import time
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal

from . import config

# USD per 1M tokens: (input, cached_input, output). Sources:
#   Meta: https://dev.meta.ai/docs/pricing-rate-limits
#   Baseten: https://www.baseten.co/library/muse-spark-open/
PRICES = {
    "muse-spark-1.3": (1.25, 0.15, 4.25),
    "muse-spark-1.3-contributor": (0.10, 0.002, 0.20),
    "meta-models/muse-spark-open-1026": (1.25, 0.15, 4.25),
}


def estimate_cost(model: str, prompt_tokens: int, completion_tokens: int, cached_tokens: int = 0) -> float:
    inp, cached, out = PRICES.get(model, (0.0, 0.0, 0.0))
    uncached = max(prompt_tokens - cached_tokens, 0)
    return (uncached * inp + cached_tokens * cached + completion_tokens * out) / 1_000_000


def _table():
    import boto3  # Lambda runtime has it; dev-only dependency locally

    return boto3.resource("dynamodb").Table(config.USAGE_TABLE)


def _write(record: dict) -> None:
    if config.STORAGE == "dynamodb":
        day = datetime.fromtimestamp(record["ts"], timezone.utc).strftime("%Y-%m-%d")
        item = {k: Decimal(str(v)) if isinstance(v, float) else v for k, v in record.items()}
        _table().put_item(Item={"day": day, "sk": f"{record['ts']:.3f}#{uuid.uuid4().hex[:8]}", **item})
    else:
        config.LOCAL_DIR.mkdir(parents=True, exist_ok=True)
        with open(config.USAGE_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")


def _read_all():
    if config.STORAGE == "dynamodb":
        table, kwargs = _table(), {}
        while True:  # small table; a full scan is fine for a hackathon-sized log
            page = table.scan(**kwargs)
            for item in page["Items"]:
                yield {k: float(v) if isinstance(v, Decimal) else v for k, v in item.items()}
            if "LastEvaluatedKey" not in page:
                return
            kwargs["ExclusiveStartKey"] = page["LastEvaluatedKey"]
    elif config.USAGE_LOG.exists():
        for line in config.USAGE_LOG.read_text(encoding="utf-8").splitlines():
            if line.strip():
                yield json.loads(line)


def records_for_days(days: list[str]):
    """Usage records for the given UTC days ("YYYY-MM-DD"): one small query per day, never a scan."""
    if config.STORAGE == "dynamodb":
        from boto3.dynamodb.conditions import Key

        table = _table()
        for day in days:
            kwargs = {}
            while True:
                page = table.query(KeyConditionExpression=Key("day").eq(day),
                                   ProjectionExpression="cost_usd, purpose", **kwargs)
                for item in page["Items"]:
                    yield {k: float(v) if isinstance(v, Decimal) else v for k, v in item.items()}
                if "LastEvaluatedKey" not in page:
                    break
                kwargs["ExclusiveStartKey"] = page["LastEvaluatedKey"]
        return
    wanted = set(days)
    for r in _read_all():
        if datetime.fromtimestamp(r["ts"], timezone.utc).strftime("%Y-%m-%d") in wanted:
            yield r


def log_call(provider: str, model: str, prompt_tokens: int, completion_tokens: int,
             cached_tokens: int = 0, purpose: str = "", cache_hit: bool = False) -> dict:
    record = {
        "ts": time.time(),
        "provider": provider,
        "model": model,
        "purpose": purpose,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "cached_tokens": cached_tokens,
        "cache_hit": cache_hit,
        "cost_usd": 0.0 if cache_hit else estimate_cost(model, prompt_tokens, completion_tokens, cached_tokens),
    }
    try:
        _write(record)
    except Exception as e:  # never fail a user request because the usage log is down
        print(f"usage log write failed: {e}")
    return record


def log_extra(provider: str, model: str, cost_usd: float, purpose: str = "") -> dict | None:
    """A cost that isn't tokens, e.g. web search queries ($2.50 per 1,000). Counts toward the daily budget."""
    if not cost_usd:
        return None
    record = {"ts": time.time(), "provider": provider, "model": model, "purpose": purpose, "prompt_tokens": 0,
              "completion_tokens": 0, "cached_tokens": 0, "cache_hit": False, "cost_usd": cost_usd}
    try:
        _write(record)
    except Exception as e:
        print(f"usage log write failed: {e}")
    return record


AUDIO_USD_PER_HOUR ={"muse-voice-transcribe-1.0": 0.18}  # billed on whole seconds of audio


def log_audio(model: str, audio_ms: int, purpose: str = "") -> dict:
    """Speech-to-text is billed per second of audio, not per token."""
    audio_seconds = math.ceil(audio_ms / 1000)
    record = {"ts": time.time(), "provider": "meta", "model": model, "purpose": purpose,
              "prompt_tokens": 0, "completion_tokens": 0, "cached_tokens": 0, "cache_hit": False,
              "audio_seconds": audio_seconds,
              "cost_usd": audio_seconds * AUDIO_USD_PER_HOUR.get(model, 0.0) / 3600}
    try:
        _write(record)
    except Exception as e:
        print(f"usage log write failed: {e}")
    return record


def totals() -> dict:
    """Spend per provider and model, plus call counts."""
    by_model = defaultdict(lambda: {"calls": 0, "cache_hits": 0, "prompt_tokens": 0,
                                    "completion_tokens": 0, "cost_usd": 0.0})
    for r in _read_all():
        m = by_model[(r["provider"], r["model"])]
        m["calls"] += 1
        m["cache_hits"] += int(bool(r.get("cache_hit", False)))
        if r.get("cache_hit"):
            continue  # cached replays cost nothing; don't double-count their tokens
        m["prompt_tokens"] += int(r["prompt_tokens"])
        m["completion_tokens"] += int(r["completion_tokens"])
        m["cost_usd"] += r["cost_usd"]
    return dict(by_model)
