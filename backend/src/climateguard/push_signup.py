"""Web push sign-up and sign-out: the same style of limits as email sign-up.

A device (its push endpoint) holds one subscription for one zone and one language; subscribing again from
the same device replaces it. Limits are checked before any NWS lookup, so abuse can't become API calls.
Unlike email there is no confirmation step: the person tapped "allow" on their own phone.
"""
import logging

from . import config, push_store, ratelimit, zones
from .languages import is_supported
from .push_store import PushError
from .subscriptions import SignupError, _locate

log = logging.getLogger(__name__)

PER_IP_PER_HOUR = 5
PER_ENDPOINT_PER_DAY = 10
GLOBAL_PER_DAY = 300
UNSUB_PER_IP_PER_HOUR = 30


def _validated(subscription) -> dict:
    try:
        return push_store.validate_subscription(subscription)
    except PushError as e:
        raise SignupError(e.code, e.status) from None


def subscribe(subscription, lang: str, ip: str, zip_code: str | None = None, lat=None, lon=None) -> dict:
    sub = _validated(subscription)
    if not is_supported(lang):
        raise SignupError("invalid_lang", 400)
    if not zip_code and (lat is None or lon is None):
        raise SignupError("missing_location", 400)

    if not ratelimit.hit("push-ip", ip, PER_IP_PER_HOUR, 3600):
        raise SignupError("rate_limited", 429)
    if not ratelimit.hit("push-endpoint", sub["endpoint"], PER_ENDPOINT_PER_DAY, 86400):
        raise SignupError("rate_limited", 429)
    if not ratelimit.hit("push-global", "all", GLOBAL_PER_DAY, 86400):
        raise SignupError("busy", 503)

    zone = _locate(zip_code, lat, lon)

    existing = push_store.get_pointer(sub["endpoint"])
    claimed = False
    if existing is None:  # a device already subscribed keeps its slot when it changes place or language
        if not ratelimit.claim_push_slot(config.MAX_PUSH_SUBSCRIBERS):
            raise SignupError("subscriber_cap", 503)
        claimed = True
    try:
        if existing and (existing["target_zone"], existing["lang"]) != (zone["zone"], lang):
            push_store.delete(sub["endpoint"])  # replaced: one place and language per device
        push_store.put(zone["zone"], lang, sub)
        zones.add_language(zone["zone"], lang)
        zones.ensure_confirmed(zone["zone"], 1)  # monitored from the next collection run
    except Exception:
        if claimed:
            try:
                ratelimit.release_push_slot()
            except Exception:
                log.exception("failed to release push slot after sign-up failure")
        raise
    return {"status": "subscribed", "zone": zone["zone"], "zone_name": zone["name"], "place": zone.get("place"),
            "lang": lang}


def unsubscribe(endpoint, ip: str) -> dict:
    """Needs the subscription's endpoint itself (nothing else identifies a device). Always answers the same way,
    so it can't be used to check whether an endpoint is subscribed."""
    try:
        endpoint = push_store.validate_endpoint(endpoint)
    except PushError as e:
        raise SignupError(e.code, e.status) from None
    if not ratelimit.hit("push-unsub-ip", ip, UNSUB_PER_IP_PER_HOUR, 3600):
        raise SignupError("rate_limited", 429)
    if push_store.delete(endpoint) is not None:
        ratelimit.release_push_slot()
    return {"status": "unsubscribed"}
