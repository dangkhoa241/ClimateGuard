"""Send ONE test notification to phone-notification (web push) subscribers. Local admin tool: it runs on your
machine with your AWS credentials, reads the subscriptions from DynamoDB and the VAPID private key from SSM at
runtime (the key is never printed), and adds no API route.

Usage (from the repo root):
  python backend/scripts/send_test_push.py                 # the most recent subscription
  python backend/scripts/send_test_push.py --zip 95202     # every subscription in that ZIP code's zone
  python backend/scripts/send_test_push.py --dry-run       # show who would get it, send nothing
  python backend/scripts/send_test_push.py --open-url http://localhost:5173   # tap opens the local app

The notification says "ClimateGuard test notification" in the subscription's language. Tapping it opens
<open-url>/?zone=<ZONE>&lang=<lang>. A phone only opens links on the site it subscribed from, so when you
subscribed at localhost pass --open-url http://localhost:5173. Nothing is removed unless you pass --prune
(then subscriptions the push service reports as gone, 404 or 410, are deleted like the collector does).
Output shows zones, languages and counts only, never endpoints or keys.
"""
import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

APP_URL = "https://climate-guard-khaki.vercel.app"
PARAM = "/climateguard/vapid-private-key"
BODY = {  # zh/tl/ko/ar: simple machine-style translations, like the rest of the automatic text
    "en": "ClimateGuard test notification",
    "es": "Notificación de prueba de ClimateGuard",
    "vi": "Thông báo thử nghiệm của ClimateGuard",
    "zh": "ClimateGuard 测试通知",
    "tl": "Pansubok na abiso ng ClimateGuard",
    "ko": "ClimateGuard 테스트 알림",
    "ar": "إشعار تجريبي من ClimateGuard",
}


def zone_for_zip(zip_code: str) -> str:
    """ZIP -> NWS zone id, without registering anything (the app's own lookup would create a zone record)."""
    from climateguard import geo, zones

    lat, lon = geo.zip_to_point(zip_code)
    for demo in zones.DEMO_ZONES.values():
        if abs(demo["lat"] - lat) < 0.02 and abs(demo["lon"] - lon) < 0.02:
            return demo["zone"]
    return zones.resolve_point(lat, lon)["zone"]


def pick_targets(subscribers: list[dict], zone: str | None) -> list[dict]:
    """All subscribers of `zone`, or with no zone the single most recent subscription."""
    if zone:
        return [s for s in subscribers if s["zone"] == zone]
    return sorted(subscribers, key=lambda s: int(s.get("created", 0)))[-1:]


def build_payload(sub: dict, open_url: str) -> dict:
    lang = sub.get("lang", "en")
    return {"title": "ClimateGuard", "body": BODY.get(lang, BODY["en"]), "lang": lang, "tag": "climateguard-test",
            "url": f"{open_url.rstrip('/')}/?zone={sub['zone']}&lang={lang}"}


def main(argv: list[str], storage: str = "dynamodb") -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--zip", help="send to every subscription in this ZIP code's zone (default: the most recent one)")
    ap.add_argument("--open-url", default=APP_URL, help="site the notification opens when tapped")
    ap.add_argument("--app-url", default=APP_URL, help="contact URL in the push signature (the live app)")
    ap.add_argument("--region", default="us-east-2")
    ap.add_argument("--param", default=PARAM, help="SSM SecureString holding the VAPID private key")
    ap.add_argument("--dry-run", action="store_true", help="list the matches, send nothing")
    ap.add_argument("--prune", action="store_true", help="delete subscriptions the push service reports as gone")
    args = ap.parse_args(argv)

    os.environ.setdefault("AWS_DEFAULT_REGION", args.region)
    from climateguard import config, push_store, ratelimit, webpush

    config.STORAGE = storage  # the real subscriptions live in DynamoDB (tests pass "local")
    config.VAPID_PRIVATE_KEY_PARAM = config.VAPID_PRIVATE_KEY_PARAM or args.param

    zone = zone_for_zip(args.zip) if args.zip else None
    targets = pick_targets(push_store.all_subscribers(), zone)
    where = f"zone {zone} (ZIP {args.zip})" if zone else "the most recent subscription"
    if not targets:
        print(f"No subscriptions found for {where}. Nothing was sent.")
        return 1
    print(f"{len(targets)} subscription(s) for {where}:")
    for s in targets:
        print(f"  zone {s['zone']}, language {s.get('lang')}")
    if args.dry_run:
        print("Dry run: nothing was sent.")
        return 0

    key = webpush.vapid_key()
    if not key:
        print(f"Cannot read the VAPID private key ({args.param}). Run make_vapid_keys.py first, and check your "
              "AWS sign-in. Nothing was sent.")
        return 1

    counts = {"sent": 0, "gone": 0, "failed": 0}
    for s in targets:
        try:
            status = webpush._send(s, json.dumps(build_payload(s, args.open_url), ensure_ascii=False), key,
                                   contact=args.app_url)
        except Exception as e:  # never print the exception text: it may hold the endpoint
            status = 0
            print(f"  send error: {type(e).__name__}")
        if 200 <= status < 300:
            counts["sent"] += 1
        elif status in (404, 410):
            counts["gone"] += 1
            if args.prune:
                push_store.delete_subscriber(s["zone"], s["lang"], push_store.endpoint_hash(s["endpoint"]))
                ratelimit.release_push_slot()
        else:
            counts["failed"] += 1
            print(f"  zone {s['zone']}, language {s.get('lang')}: push service answered {status or 'nothing'}")
    del key
    gone_note = " (removed)" if args.prune and counts["gone"] else ""
    print(f"Sent {counts['sent']}, gone {counts['gone']}{gone_note}, failed {counts['failed']}.")
    return 0 if counts["sent"] else 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main(sys.argv[1:]))
