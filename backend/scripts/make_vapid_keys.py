"""Create the web push (VAPID) key pair. The private key goes straight into SSM Parameter Store as a
SecureString; only the PUBLIC key is printed. The private key is never printed, written to a file, or logged.

Usage:
  python scripts/make_vapid_keys.py                  # create /climateguard/vapid-private-key in us-east-2
  python scripts/make_vapid_keys.py --show-public    # print the public key of the stored private key
  python scripts/make_vapid_keys.py --force          # replace the key (every phone must turn notifications on again)

Put the printed public key in the frontend as VITE_VAPID_PUBLIC_KEY (Vercel environment variable, and
frontend/.env.local for local runs). Needs AWS credentials that can call ssm:PutParameter / ssm:GetParameter.
"""
import argparse
import base64
import sys

PARAM = "/climateguard/vapid-private-key"
REGION = "us-east-2"


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def generate_pair() -> tuple[str, str]:
    """(private, public): the raw 32-byte private scalar and the 65-byte uncompressed public point, base64url."""
    from cryptography.hazmat.primitives.asymmetric import ec

    key = ec.generate_private_key(ec.SECP256R1())
    private = _b64(key.private_numbers().private_value.to_bytes(32, "big"))
    return private, public_from_private(private)


def public_from_private(private_b64: str) -> str:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec

    value = int.from_bytes(base64.urlsafe_b64decode(private_b64 + "=" * (-len(private_b64) % 4)), "big")
    key = ec.derive_private_key(value, ec.SECP256R1())
    return _b64(key.public_key().public_bytes(serialization.Encoding.X962,
                                              serialization.PublicFormat.UncompressedPoint))


def main(argv: list[str], client=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--region", default=REGION)
    ap.add_argument("--name", default=PARAM)
    ap.add_argument("--force", action="store_true", help="replace an existing key")
    ap.add_argument("--show-public", action="store_true", help="print the public key of the stored private key")
    args = ap.parse_args(argv)
    if client is None:
        import boto3

        client = boto3.client("ssm", region_name=args.region)

    if args.show_public:
        value = client.get_parameter(Name=args.name, WithDecryption=True)["Parameter"]["Value"]
        print(f"Public key: {public_from_private(value)}")
        return 0

    exists = True
    try:
        client.get_parameter(Name=args.name)  # no decryption: only checks that it exists
    except Exception as e:
        if type(e).__name__ != "ParameterNotFound":
            raise
        exists = False
    if exists and not args.force:
        print(f"{args.name} already exists, so nothing was changed. Use --show-public to print its public key, "
              "or --force to replace it (this signs out every phone).", file=sys.stderr)
        return 1

    private, public = generate_pair()
    client.put_parameter(Name=args.name, Value=private, Type="SecureString", Overwrite=args.force,
                         Description="ClimateGuard web push (VAPID) private key")
    del private
    print(f"Stored the private key in SSM as a SecureString: {args.name} ({args.region})")
    print(f"Public key: {public}")
    print("Set it in the frontend as VITE_VAPID_PUBLIC_KEY.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
