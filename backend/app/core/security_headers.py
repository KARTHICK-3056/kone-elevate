"""Security response headers, applied to every response.

The P4 finding this closes: no security headers on any tier. This API has
no nginx layer of its own (the frontend's does - see frontend/nginx.conf);
these headers are the backend's half of that, and matter independently
because the API is reachable directly (Swagger at /docs, direct API
clients), not only through the frontend's proxy.
"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

#: Swagger UI (/docs) and ReDoc (/redoc) load their JS/CSS from a CDN and
#: inline-render, which a locked-down CSP breaks. Every other route gets the
#: strict default; these two get no CSP at all rather than a weakened one
#: quietly applied everywhere.
_DOCS_PATHS = {"/docs", "/redoc"}

_DEFAULT_CSP = "default-src 'none'; frame-ancestors 'none'"


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        # Only takes effect over TLS in a browser - harmless to send over
        # plain HTTP in local development, and one less thing to remember
        # to add when a deployment does terminate TLS.
        response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
        if request.url.path not in _DOCS_PATHS:
            response.headers["Content-Security-Policy"] = _DEFAULT_CSP
        return response
