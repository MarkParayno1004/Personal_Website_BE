import time
from collections import defaultdict, deque
from fastapi import HTTPException, Request, status

# shortcut: in-memory and per-process; move counters to Redis if you run more than one instance.
_hits: dict[tuple[str, str], deque] = defaultdict(deque)


def rate_limit(name: str, max_requests: int, window_seconds: int):
    """Dependency factory: allow `max_requests` per client IP per `window_seconds` for the named bucket."""

    def dependency(request: Request) -> None:
        key = (request.client.host if request.client else "unknown", name)
        now = time.monotonic()
        hits = _hits[key]
        while hits and now - hits[0] > window_seconds:
            hits.popleft()
        if len(hits) >= max_requests:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many attempts. Please try again later.",
            )
        hits.append(now)

    return dependency


login_limiter = rate_limit("login", max_requests=10, window_seconds=60)
register_limiter = rate_limit("register", max_requests=5, window_seconds=60)
# Shared by verification / password-reset endpoints: they send email or accept single-use links.
email_limiter = rate_limit("email", max_requests=5, window_seconds=60)
