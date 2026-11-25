"""Upload a `viralclip publish` output to Cloudflare R2: game files first, the index last.

Game files have immutable content-hashed names, so they are cached for a year; the index
is revalidated on every request. Pruning uses the index that was live on R2 before this
upload: its files and the new ones stay, other game files go only after the grace period.
boto3 is imported lazily because collector installs do not ship it; install it in the
publisher environment only. Credentials come from the environment, never from arguments.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

from viralclip.publish import GAME_FILE, GRACE_SECONDS

INDEX = "index.json"
GAME_CACHE = "public, max-age=31536000, immutable"
INDEX_CACHE = "no-cache"
ENV = ("R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY")


def _local_index(source: Path) -> tuple[bytes, list[str]]:
    """Read and check the local publication before anything is sent."""
    raw = (source / INDEX).read_bytes()
    files = [game.get("file", "") for game in json.loads(raw)["games"]]
    if not files or any(not GAME_FILE.fullmatch(name) for name in files):
        raise ValueError("The local index must list content-hashed game files")
    missing = [name for name in files if not (source / name).is_file()]
    if missing:
        raise ValueError(f"Game files missing from the local publication: {missing}")
    return raw, files


def _remote_files(client, bucket: str, key: str) -> set[str]:
    """Game files named by the index currently live on R2 (none before the first upload)."""
    try:
        body = client.get_object(Bucket=bucket, Key=key)["Body"].read()
    except client.exceptions.NoSuchKey:
        return set()
    return {
        game["file"]
        for game in json.loads(body)["games"]
        if GAME_FILE.fullmatch(game.get("file", ""))
    }


def _listing(client, bucket: str, prefix: str):
    token = None
    while True:
        extra = {"ContinuationToken": token} if token else {}
        page = client.list_objects_v2(Bucket=bucket, Prefix=prefix, **extra)
        yield from page.get("Contents", [])
        if not page.get("IsTruncated"):
            return
        token = page["NextContinuationToken"]


def upload(
    source: Path, bucket: str, client, *, prefix: str = "rankings/", now: datetime | None = None
) -> dict:
    """Upload `source` (a publish `rankings/` directory) and return what changed."""
    raw, files = _local_index(source)
    previous = _remote_files(client, bucket, prefix + INDEX)
    for name in files:
        client.put_object(
            Bucket=bucket,
            Key=prefix + name,
            Body=(source / name).read_bytes(),
            ContentType="application/json",
            CacheControl=GAME_CACHE,
        )
    # The index goes last, so a failed upload leaves the live index and its files intact.
    client.put_object(
        Bucket=bucket,
        Key=prefix + INDEX,
        Body=raw,
        ContentType="application/json",
        CacheControl=INDEX_CACHE,
    )
    keep = previous | set(files)
    horizon = (now or datetime.now(UTC)) - timedelta(seconds=GRACE_SECONDS)
    pruned = []
    for item in _listing(client, bucket, prefix):
        name = item["Key"][len(prefix) :]
        if GAME_FILE.fullmatch(name) and name not in keep and item["LastModified"] < horizon:
            client.delete_object(Bucket=bucket, Key=item["Key"])
            pruned.append(name)
    return {"uploaded": [*files, INDEX], "kept_previous": sorted(previous), "pruned": pruned}


def client_from_environment():
    values = [os.environ.get(name) for name in ENV]
    if not all(values):
        raise ValueError(f"Set {', '.join(ENV)} in the publisher environment")
    import boto3  # lazy: publisher-only dependency

    account, key_id, secret = values
    return boto3.client(
        "s3",
        endpoint_url=f"https://{account}.r2.cloudflarestorage.com",
        aws_access_key_id=key_id,
        aws_secret_access_key=secret,
        region_name="auto",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m viralclip.r2", description=__doc__)
    parser.add_argument("--source", type=Path, required=True, help="publish output rankings/")
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--prefix", default="rankings/")
    args = parser.parse_args(argv)
    try:
        result = upload(args.source, args.bucket, client_from_environment(), prefix=args.prefix)
    except (OSError, ValueError, ImportError) as exc:
        parser.exit(1, f"R2 upload failed: {exc}\n")
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
