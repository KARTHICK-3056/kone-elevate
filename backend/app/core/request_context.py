"""Per-request context propagated into log records: the request id.

A single ``contextvars.ContextVar`` rather than thread-local storage,
because ASGI request handling can hop across ``await`` points on the same
thread - thread-local state would leak between concurrently-handled
requests on one worker.
"""

from __future__ import annotations

from contextvars import ContextVar
from typing import Optional

_request_id: ContextVar[Optional[str]] = ContextVar("request_id", default=None)


def get_request_id() -> Optional[str]:
    return _request_id.get()


def set_request_id(value: Optional[str]) -> None:
    _request_id.set(value)
