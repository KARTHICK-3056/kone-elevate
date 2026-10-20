"""Request-id middleware: the thread that ties one request's logs together.

Before this, a JSON log line had no way to be grouped with every other line
touched by the same request - the P4 finding was explicit about it:
"structured JSON logging with a request id threaded through every layer."
Accepting an inbound ``X-Request-ID`` (rather than always minting a new one)
lets a request be traced end-to-end when a caller or an upstream proxy
already assigns one.
"""

from __future__ import annotations

import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.core.request_context import set_request_id

REQUEST_ID_HEADER = "X-Request-ID"


class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = request.headers.get(REQUEST_ID_HEADER) or uuid.uuid4().hex
        set_request_id(request_id)
        response = await call_next(request)
        response.headers[REQUEST_ID_HEADER] = request_id
        return response
