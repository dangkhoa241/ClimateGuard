"""Sign-up for email alerts via Amazon SNS, grouped by NWS forecast zone and language.

One SNS topic per (zone, language), e.g. "climateguard-caz159-es", created on first use
(CreateTopic is idempotent). SNS email subscriptions give us:
  - double opt-in: SNS emails a confirmation link; nothing is delivered until it's clicked
  - an unsubscribe link at the bottom of every message
Only zones with at least one CONFIRMED subscription (plus the demo zones) are monitored;
refresh_confirmed() recounts them from SNS.
NOTIFY_MODE=dryrun (local dev) records sign-ups to backend/.local/outbox.jsonl instead
and treats them as confirmed.
"""
import json
import logging
import re
import time
from functools import lru_cache

from . import config, ratelimit, zones
from .geo import GeoError
from .languages import is_supported

EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[A-Za-z0-9.-]{1,255}\.[A-Za-z]{2,24}$")

# Abuse limits (each sign-up makes SNS send an email, so keep these tight)
PER_IP_PER_HOUR = 5
PER_EMAIL_PER_DAY = 3
GLOBAL_PER_DAY = 300
log = logging.getLogger(__name__)


class SignupError(Exception):
    def __init__(self, code: str, status: int):
        super().__init__(code)
        self.code, self.status = code, status


def topic_name(zone: str, lang: str) -> str:
    return f"{config.SNS_TOPIC_PREFIX}-{zone.lower()}-{lang}"


@lru_cache(maxsize=None)
def topic_arn(zone: str, lang: str) -> str:
    import boto3

    resp = boto3.client("sns").create_topic(
        Name=topic_name(zone, lang),
        Attributes={"DisplayName": "ClimateGuard"},  # shown as the email sender name
        Tags=[{"Key": "app", "Value": "climateguard"}],
    )
    return resp["TopicArn"]


def outbox(record: dict) -> None:
    config.LOCAL_DIR.mkdir(parents=True, exist_ok=True)
    with open(config.LOCAL_DIR / "outbox.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": time.time(), **record}, ensure_ascii=False) + "\n")


def _locate(zip_code, lat, lon) -> dict:
    try:
        return zones.locate(zip_code=zip_code, lat=lat, lon=lon)
    except GeoError as e:
        raise SignupError(e.code, 400) from None
    except zones.ZoneError as e:
        raise SignupError(e.code, 503 if e.code == "nws_unavailable" else 400) from None


def subscribe(email: str, lang: str, ip: str, zip_code: str | None = None, lat=None, lon=None) -> dict:
    email = (email or "").strip()
    if not EMAIL_RE.match(email) or len(email) > 254:
        raise SignupError("invalid_email", 400)
    if not is_supported(lang):
        raise SignupError("invalid_lang", 400)
    if not zip_code and (lat is None or lon is None):
        raise SignupError("missing_location", 400)

    # Limits come before the location lookup, so abuse can't turn into NWS API calls.
    if not ratelimit.hit("signup-ip", ip, PER_IP_PER_HOUR, 3600):
        raise SignupError("rate_limited", 429)
    if not ratelimit.hit("signup-email", email, PER_EMAIL_PER_DAY, 86400):
        raise SignupError("rate_limited", 429)
    if not ratelimit.hit("signup-global", "all", GLOBAL_PER_DAY, 86400):
        raise SignupError("busy", 503)

    zone = _locate(zip_code, lat, lon)

    sub_id = f"{email}|{zone['zone']}|{lang}"
    claim = ratelimit.claim_subscription(email, sub_id, config.MAX_SUBSCRIPTIONS_PER_EMAIL,
                                         config.MAX_SUBSCRIBERS)
    if claim == "email_subscription_cap":
        raise SignupError("email_subscription_cap", 429)
    if claim == "subscriber_cap":
        raise SignupError("subscriber_cap", 503)

    try:
        if config.NOTIFY_MODE == "sns":
            import boto3

            boto3.client("sns").subscribe(TopicArn=topic_arn(zone["zone"], lang), Protocol="email",
                                         Endpoint=email)
        else:
            outbox({"type": "subscribe", "zone": zone["zone"], "lang": lang,
                    "email_hash": ratelimit.hashed(email)})
        zones.add_language(zone["zone"], lang)
    except Exception:
        if claim == "created":
            try:
                ratelimit.release_subscription(email, sub_id)
            except Exception:
                log.exception("failed to release subscription claim after setup failure")
        raise
    return {"status": "pending_confirmation", "zone": zone["zone"], "zone_name": zone["name"],
            "place": zone.get("place"), "lang": lang}


def _confirmed_in_topic(zone: str, lang: str) -> int:
    import boto3

    sns, count, token = boto3.client("sns"), 0, None
    while True:
        kw = {"TopicArn": topic_arn(zone, lang), **({"NextToken": token} if token else {})}
        page = sns.list_subscriptions_by_topic(**kw)
        count += sum(1 for s in page["Subscriptions"] if s["SubscriptionArn"].startswith("arn:"))
        token = page.get("NextToken")
        if not token:
            return count


def _confirmed_local(zone: str) -> int:
    path = config.LOCAL_DIR / "outbox.jsonl"
    if not path.exists():
        return 0
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return len({r["email_hash"] + r["lang"] for r in rows if r.get("type") == "subscribe" and r.get("zone") == zone})


def refresh_confirmed(max_age_minutes: int | None = None) -> list[str]:
    """Recount confirmed subscriptions for registered zones whose count is older than
    `max_age_minutes`. Returns the zones whose count changed."""
    max_age = config.ACTIVE_REFRESH_MINUTES if max_age_minutes is None else max_age_minutes
    changed = []
    for rec in zones.all_zones():
        if not rec.get("langs") or time.time() - (rec.get("confirmed_checked_at") or 0) < max_age * 60:
            continue
        if config.NOTIFY_MODE == "sns":
            n = sum(_confirmed_in_topic(rec["zone"], lang) for lang in rec["langs"])
        else:
            n = _confirmed_local(rec["zone"])
        if n != rec.get("confirmed"):
            changed.append(rec["zone"])
        zones.put({**rec, "confirmed": n, "confirmed_checked_at": int(time.time())})
    return changed
