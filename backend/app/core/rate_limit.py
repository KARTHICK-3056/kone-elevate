"""In-memory rate limiting for the endpoints where a miss is expensive.

Applied only to login and signup (see ``app.api.auth``) - the cost of
missing here is credential stuffing or OTP-guessing at scale, not every
endpoint indiscriminately rate limited regardless of what it costs to abuse.

Honest scope: single-process, in-memory. Correct for the one-worker
deployment this prototype's Dockerfile/docker-compose.yml actually run.
The moment more than one worker process serves traffic, each process
counts independently and the *effective* limit multiplies by worker count -
a real deployment needs a shared store (Redis, most commonly) behind this
same ``enforce`` interface, which is why the limiter logic is isolated
here rather than inlined into the endpoints.
"""

from __future__ import annotations

import time
from collections import defaultdict
from threading import Lock
from typing import Dict, List, Tuple

from fastapi import HTTPException, Request, status

from app.core.config import settings

_lock = Lock()
_windows: Dict[Tuple[str, str], List[float]] = defaultdict(list)


def _client_key(request: Request) -> str:
    """Best-effort caller identity: the first hop in X-Forwarded-For, or
    the direct peer address. A reverse proxy in front of this API should
    set X-Forwarded-For itself and strip any client-supplied one - that
    trust boundary lives at the proxy, not here.
    """
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def enforce(request: Request, bucket: str, max_requests: int) -> None:
    """Raise 429 once ``bucket`` has seen ``max_requests`` hits from this
    caller inside the configured window; otherwise record this hit."""
    key = (bucket, _client_key(request))
    now = time.monotonic()
    window = settings.RATE_LIMIT_WINDOW_SECONDS
    with _lock:
        hits = _windows[key]
        cutoff = now - window
        while hits and hits[0] < cutoff:
            hits.pop(0)
        if len(hits) >= max_requests:
            retry_after = max(1, int(window - (now - hits[0])))
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Too many requests. Try again in {retry_after}s.",
                headers={"Retry-After": str(retry_after)},
            )
        hits.append(now)


def login_rate_limit(request: Request) -> None:
    enforce(request, "login", settings.RATE_LIMIT_LOGIN_MAX)


def signup_rate_limit(request: Request) -> None:
    enforce(request, "signup", settings.RATE_LIMIT_SIGNUP_MAX)
