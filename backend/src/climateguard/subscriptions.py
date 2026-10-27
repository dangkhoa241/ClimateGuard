"""City sign-up for email alerts via Amazon SNS.

One SNS topic per (city, language), e.g. "climateguard-stockton-es", created on
first use (CreateTopic is idempotent). SNS email subscriptions give us:
  - double opt-in: SNS emails a confirmation link; nothing is delivered until it's clicked
  - an unsubscribe link at the bottom of every message
NOTIFY_MODE=dryrun (local dev) records sign-ups to backend/.local/outbox.jsonl instead.
"""
import json
import re
import time
from functools import lru_cache

from . import config, ratelimit
from .cities import CITIES

LANGS = ("en", "es", "vi")
EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[A-Za-z0-9.-]{1,255}\.[A-Za-z]{2,24}$")

# Abuse limits (each sign-up makes SNS send an email, so keep these tight)
PER_IP_PER_HOUR = 5
PER_EMAIL_PER_DAY = 3
GLOBAL_PER_DAY = 300


class SignupError(Exception):
    def __init__(self, code: str, status: int):
        super().__init__(code)
        self.code, self.status = code, status


def topic_name(city: str, lang: str) -> str:
    return f"{config.SNS_TOPIC_PREFIX}-{city}-{lang}"


@lru_cache(maxsize=None)
def topic_arn(city: str, lang: str) -> str:
    import boto3

    resp = boto3.client("sns").create_topic(
        Name=topic_name(city, lang),
        Attributes={"DisplayName": "ClimateGuard"},  # shown as the email sender name
        Tags=[{"Key": "app", "Value": "climateguard"}],
    )
    return resp["TopicArn"]


def outbox(record: dict) -> None:
    config.LOCAL_DIR.mkdir(parents=True, exist_ok=True)
    with open(config.LOCAL_DIR / "outbox.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": time.time(), **record}, ensure_ascii=False) + "\n")


def subscribe(email: str, city: str, lang: str, ip: str) -> dict:
    email = (email or "").strip()
    if not EMAIL_RE.match(email) or len(email) > 254:
        raise SignupError("invalid_email", 400)
    if city not in CITIES:
        raise SignupError("invalid_city", 400)
    if lang not in LANGS:
        raise SignupError("invalid_lang", 400)

    if not ratelimit.hit("signup-ip", ip, PER_IP_PER_HOUR, 3600):
        raise SignupError("rate_limited", 429)
    if not ratelimit.hit("signup-email", email, PER_EMAIL_PER_DAY, 86400):
        raise SignupError("rate_limited", 429)
    if not ratelimit.hit("signup-global", "all", GLOBAL_PER_DAY, 86400):
        raise SignupError("busy", 503)

    # Repeat sign-ups (same email, city and language) don't count toward the cap; SNS
    # just re-sends the confirmation email if it's still pending.
    sub_id = f"{email}|{city}|{lang}"
    if not ratelimit.seen("subscription", sub_id):
        if ratelimit.peek_counter("subscribers") >= config.MAX_SUBSCRIBERS:
            raise SignupError("subscriber_cap", 503)
        if ratelimit.mark_once("subscription", sub_id):
            ratelimit.counter("subscribers")

    if config.NOTIFY_MODE == "sns":
        import boto3

        boto3.client("sns").subscribe(TopicArn=topic_arn(city, lang), Protocol="email", Endpoint=email)
    else:
        outbox({"type": "subscribe", "city": city, "lang": lang, "email_hash": ratelimit.hashed(email)})
    return {"status": "pending_confirmation", "city": city, "lang": lang}
