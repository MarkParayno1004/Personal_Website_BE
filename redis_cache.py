import json
import logging
import os
import time
from typing import Any, Optional
import redis

logger = logging.getLogger("redis_cache")

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
CACHE_TTL_SECONDS = int(os.getenv("CACHE_TTL_SECONDS", "3600"))  # Default 1 hour TTL
RETRY_BACKOFF_SECONDS = 30  # Don't retry failed Redis connection for 30s to keep API fast

_redis_client: Optional[redis.Redis] = None
_last_connect_attempt: float = 0
_redis_disabled: bool = False


def get_redis_client() -> Optional[redis.Redis]:
    """
    Get or initialize Redis client connection.
    Fails gracefully and avoids retrying immediately if Redis is unavailable.
    """
    global _redis_client, _last_connect_attempt, _redis_disabled
    now = time.time()

    if _redis_client is not None:
        try:
            _redis_client.ping()
            return _redis_client
        except Exception:
            _redis_client = None
            _redis_disabled = True
            _last_connect_attempt = now
            return None

    # Avoid blocking requests when Redis is offline
    if _redis_disabled and (now - _last_connect_attempt < RETRY_BACKOFF_SECONDS):
        return None

    try:
        _last_connect_attempt = now
        client = redis.Redis.from_url(
            REDIS_URL,
            decode_responses=True,
            socket_timeout=0.2,
            socket_connect_timeout=0.2,
        )
        client.ping()
        _redis_client = client
        _redis_disabled = False
        return _redis_client
    except Exception as e:
        if not _redis_disabled:
            logger.warning(f"[Redis] Could not connect to Redis at {REDIS_URL}: {e}. Caching disabled for {RETRY_BACKOFF_SECONDS}s.")
        _redis_disabled = True
        _redis_client = None
        return None


def get_cache(key: str) -> Optional[Any]:
    """Retrieve JSON-deserialized data from Redis cache."""
    try:
        client = get_redis_client()
        if client:
            cached_val = client.get(key)
            if cached_val:
                return json.loads(cached_val)
    except Exception as e:
        logger.warning(f"[Redis Cache Error] GET {key} failed: {e}")
    return None


def set_cache(key: str, data: Any, ttl: int = CACHE_TTL_SECONDS) -> None:
    """Store JSON-serializable data in Redis cache with a TTL (seconds)."""
    try:
        client = get_redis_client()
        if client:
            client.setex(key, ttl, json.dumps(data, default=str))
    except Exception as e:
        logger.warning(f"[Redis Cache Error] SET {key} failed: {e}")


def delete_cache(key: str) -> None:
    """Delete a specific key from Redis cache."""
    try:
        client = get_redis_client()
        if client:
            client.delete(key)
    except Exception as e:
        logger.warning(f"[Redis Cache Error] DELETE {key} failed: {e}")


def delete_cache_pattern(pattern: str) -> None:
    """Delete all keys matching a glob pattern."""
    try:
        client = get_redis_client()
        if client:
            keys = client.keys(pattern)
            if keys:
                client.delete(*keys)
    except Exception as e:
        logger.warning(f"[Redis Cache Error] DELETE PATTERN {pattern} failed: {e}")
