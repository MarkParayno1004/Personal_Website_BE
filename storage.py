"""File storage: Cloudflare R2 (S3-compatible) when configured, local disk otherwise.

Public files (profile pictures) get a URL anyone can open. Private files (CVs) are only
ever read back through an authenticated endpoint; their keys are never exposed.
"""
import logging
import os
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("storage")

R2_ACCOUNT_ID = os.getenv("R2_ACCOUNT_ID")
R2_ACCESS_KEY_ID = os.getenv("R2_ACCESS_KEY_ID")
R2_SECRET_ACCESS_KEY = os.getenv("R2_SECRET_ACCESS_KEY")
R2_BUCKET = os.getenv("R2_BUCKET")
R2_PUBLIC_BASE_URL = (os.getenv("R2_PUBLIC_BASE_URL") or "").rstrip("/")
# A bucket with public access exposes every key in it, so private files belong in a bucket without it.
R2_PRIVATE_BUCKET = os.getenv("R2_PRIVATE_BUCKET") or R2_BUCKET

USE_R2 = all([R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET, R2_PUBLIC_BASE_URL])
if USE_R2 and R2_PRIVATE_BUCKET == R2_BUCKET:
    logger.warning(
        "R2_PRIVATE_BUCKET is not set: private files share R2_BUCKET. If that bucket has public access, "
        "CVs are protected only by their random key names."
    )

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
# Local fallback: PUBLIC_DIR is served by the /uploads StaticFiles mount, PRIVATE_DIR is never served.
PUBLIC_DIR = os.path.join(PROJECT_ROOT, "uploads")
PRIVATE_DIR = os.path.join(PROJECT_ROOT, "private_uploads")
LOCAL_PUBLIC_PREFIX = "/uploads/"

_client = None


def _r2():
    global _client
    if _client is None:
        import boto3

        _client = boto3.client(
            "s3",
            endpoint_url=f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
            aws_access_key_id=R2_ACCESS_KEY_ID,
            aws_secret_access_key=R2_SECRET_ACCESS_KEY,
            region_name="auto",
        )
    return _client


def _local_path(root: str, key: str) -> str:
    """Resolve key under root, refusing anything that escapes it (e.g. '..' or absolute paths)."""
    path = os.path.realpath(os.path.join(root, key))
    if not path.startswith(os.path.realpath(root) + os.sep):
        raise ValueError(f"Invalid storage key: {key!r}")
    return path


def _write_local(root: str, key: str, data: bytes) -> None:
    path = _local_path(root, key)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)


def _delete_local(root: str, key: str) -> None:
    path = _local_path(root, key)
    if os.path.exists(path):
        os.remove(path)


def public_url(key: str) -> str:
    return f"{R2_PUBLIC_BASE_URL}/{key}" if USE_R2 else f"{LOCAL_PUBLIC_PREFIX}{key}"


def put_public(key: str, data: bytes, content_type: str) -> str:
    """Store a publicly readable file and return its URL."""
    if USE_R2:
        _r2().put_object(Bucket=R2_BUCKET, Key=key, Body=data, ContentType=content_type)
    else:
        _write_local(PUBLIC_DIR, key, data)
    return public_url(key)


def delete_public(url: str | None) -> None:
    """Delete a file previously returned by put_public. URLs from another backend (legacy rows) are ignored."""
    prefix = public_url("")
    if not url or not url.startswith(prefix):
        return
    key = url[len(prefix):]
    try:
        if USE_R2:
            _r2().delete_object(Bucket=R2_BUCKET, Key=key)
        else:
            _delete_local(PUBLIC_DIR, key)
    except Exception as e:  # a leftover file must never fail the request that replaced it
        logger.warning(f"[Storage] delete of public {key!r} failed: {e}")


def put_private(key: str, data: bytes, content_type: str) -> str:
    """Store a private file and return its key (store the key, never expose it)."""
    if USE_R2:
        _r2().put_object(Bucket=R2_PRIVATE_BUCKET, Key=key, Body=data, ContentType=content_type)
    else:
        _write_local(PRIVATE_DIR, key, data)
    return key


def get_private(key: str) -> bytes | None:
    """Read a private file, or None if it no longer exists."""
    try:
        if USE_R2:
            return _r2().get_object(Bucket=R2_PRIVATE_BUCKET, Key=key)["Body"].read()
        with open(_local_path(PRIVATE_DIR, key), "rb") as f:
            return f.read()
    except (FileNotFoundError, ValueError):
        return None
    except Exception as e:
        if getattr(e, "response", {}).get("Error", {}).get("Code") in ("NoSuchKey", "404"):
            return None
        raise


def delete_private(key: str | None) -> None:
    if not key:
        return
    try:
        if USE_R2:
            _r2().delete_object(Bucket=R2_PRIVATE_BUCKET, Key=key)
        else:
            _delete_local(PRIVATE_DIR, key)
    except Exception as e:
        logger.warning(f"[Storage] delete of private {key!r} failed: {e}")
