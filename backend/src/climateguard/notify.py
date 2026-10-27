"""Alert delivery. Phase 2: log only. Phase 3 replaces this with SNS email to city subscribers."""
import logging

log = logging.getLogger(__name__)


def deliver(city: str, severity: str, messages: dict) -> dict:
    log.info("DELIVERY (dry run, SNS arrives in Phase 3) city=%s severity=%s en=%s", city, severity,
             messages.get("en"))
    return {"channel": "dry-run", "recipients": 0}
