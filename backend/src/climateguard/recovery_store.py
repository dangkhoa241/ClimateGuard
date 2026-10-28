"""Temporary storage for recovery jobs: the photos and the job record, deleted after 24 hours.

  local    -> files under LOCAL_DIR/recovery/<job>/ (dev)
  dynamodb -> the private S3 bucket RECOVERY_BUCKET, keys jobs/<job>/... (Lambda; config.STORAGE)

Deletion: the collector runs every 15 minutes and deletes every job older than 24 hours (delete_expired),
and the person can delete their job at any time. The bucket's lifecycle rule (expire after 1 day) is only a
backstop: S3 runs it once a day, so on its own an object could live up to ~48 h.
"""
import json
import shutil
import time

from . import config

TTL_SECONDS = 24 * 3600


def _local(job: str):
    return config.LOCAL_DIR / "recovery" / job


def _s3():
    import boto3

    return boto3.client("s3")


def put(job: str, name: str, data: bytes, content_type: str) -> None:
    if config.STORAGE == "dynamodb":
        _s3().put_object(Bucket=config.RECOVERY_BUCKET, Key=f"jobs/{job}/{name}", Body=data,
                         ContentType=content_type)
    else:
        d = _local(job)
        d.mkdir(parents=True, exist_ok=True)
        (d / name).write_bytes(data)


def get(job: str, name: str) -> bytes | None:
    if config.STORAGE == "dynamodb":
        s3 = _s3()
        try:
            return s3.get_object(Bucket=config.RECOVERY_BUCKET, Key=f"jobs/{job}/{name}")["Body"].read()
        except s3.exceptions.NoSuchKey:
            return None
    p = _local(job) / name
    return p.read_bytes() if p.exists() else None


def names(job: str, prefix: str = "") -> list[str]:
    if config.STORAGE == "dynamodb":
        page = _s3().list_objects_v2(Bucket=config.RECOVERY_BUCKET, Prefix=f"jobs/{job}/{prefix}")
        return sorted(o["Key"].rsplit("/", 1)[1] for o in page.get("Contents", []))
    d = _local(job)
    return sorted(p.name for p in d.glob(f"{prefix}*")) if d.exists() else []


def put_job(rec: dict) -> None:
    put(rec["id"], "job.json", json.dumps(rec, ensure_ascii=False).encode(), "application/json")


def get_job(job: str) -> dict | None:
    raw = get(job, "job.json")
    if raw is None:
        return None
    rec = json.loads(raw)
    return None if time.time() - rec.get("created", 0) > TTL_SECONDS else rec


def delete(job: str) -> None:
    if config.STORAGE == "dynamodb":
        s3 = _s3()
        keys = [{"Key": o["Key"]} for o in s3.list_objects_v2(Bucket=config.RECOVERY_BUCKET,
                                                                Prefix=f"jobs/{job}/").get("Contents", [])]
        if keys:
            s3.delete_objects(Bucket=config.RECOVERY_BUCKET, Delete={"Objects": keys, "Quiet": True})
    else:
        shutil.rmtree(_local(job), ignore_errors=True)


def delete_expired(now: float | None = None) -> int:
    """Delete every object older than 24 hours. Returns how many objects (or local jobs) were deleted."""
    now = now or time.time()
    if config.STORAGE == "dynamodb":
        if not config.RECOVERY_BUCKET:
            return 0
        s3, old, kwargs = _s3(), [], {}
        while True:
            page = s3.list_objects_v2(Bucket=config.RECOVERY_BUCKET, Prefix="jobs/", **kwargs)
            old += [{"Key": o["Key"]} for o in page.get("Contents", [])
                    if now - o["LastModified"].timestamp() > TTL_SECONDS]
            if not page.get("IsTruncated"):
                break
            kwargs = {"ContinuationToken": page["NextContinuationToken"]}
        for i in range(0, len(old), 1000):
            s3.delete_objects(Bucket=config.RECOVERY_BUCKET, Delete={"Objects": old[i:i + 1000], "Quiet": True})
        return len(old)
    root, n = config.LOCAL_DIR / "recovery", 0
    if root.exists():
        for d in root.iterdir():
            if d.is_dir() and now - d.stat().st_mtime > TTL_SECONDS:
                shutil.rmtree(d, ignore_errors=True)
                n += 1
    return n
