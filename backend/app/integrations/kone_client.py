"""Transport for KONE's published APIs (https://dev.kone.com).

Scope of this module
--------------------
Everything here is written against KONE's own Apache-2.0 reference
implementation at github.com/konecorp/kone-api-examples, read at commit
``e597b46`` (Nov 2025). Endpoints, OAuth scopes and response field names
come from that source, not from a response this build has ever received:
**no KONE credentials exist here and no live call has ever been made.**
See ``docs/kone-integration.md`` §4.

That distinction is why the transport is split in two. ``KoneApiClient`` is
the seam:

* :class:`HttpKoneApiClient` speaks to the real service. It is the part
  that cannot be tested without an account, and is therefore kept as thin
  as possible - authenticate, GET, decode.
* :class:`RecordedKoneApiClient` replays fixtures captured in KONE's *real*
  response shapes. The adapters' mapping logic - the part that will
  actually be wrong if the published schema was misread - runs identically
  against both, so it is fully covered by contract tests today.

Auth
----
OAuth2 client-credentials against ``/api/v2/oauth2/token``. Scopes are
per-equipment: ``serviceinfo/ken:38999833`` for maintenance history,
``rtm/ken:38999833`` for telemetry, ``application/inventory`` to list what
the application may reach. A token is therefore cached *per scope set*, not
globally - a token minted for one KEN is not valid for another.
"""

from __future__ import annotations

import base64
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol, Sequence

from app.core.config import settings
from app.integrations.base import AdapterError

_FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"

#: Refresh a token this many seconds before it actually expires, so a call
#: never starts with a token that dies mid-flight.
_EXPIRY_SAFETY_MARGIN_SECONDS = 30


def equipment_scope(ken: str, product: str) -> str:
    """Build a per-equipment scope string, e.g. ``serviceinfo/ken:38999833``."""
    return f"{product}/{normalise_ken(ken)}"


def normalise_ken(ken: str) -> str:
    """Accept either ``38999833`` or ``ken:38999833`` and return the latter.

    KONE addresses equipment by KONE Equipment Number. Callers inside this
    codebase hold plain equipment ids, so both spellings arrive here.
    """
    text = str(ken).strip()
    return text if text.startswith("ken:") else f"ken:{text}"


class KoneApiClient(Protocol):
    """Fetch a JSON document from the KONE API for one equipment."""

    def get(self, path: str, scopes: Sequence[str]) -> Any:
        """GET ``path`` with a token carrying ``scopes``. Returns parsed JSON."""
        ...

    @property
    def source(self) -> str:
        """``"kone-api"`` or ``"fixture"`` - surfaced on every API response."""
        ...


class HttpKoneApiClient:
    """The real thing. Never exercised without credentials."""

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        hostname: Optional[str] = None,
        timeout: Optional[int] = None,
        base_url: Optional[str] = None,
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        host = (hostname or settings.KONE_API_HOSTNAME).strip().rstrip("/")
        #: Full origin, scheme included. Defaults to https against the
        #: configured host; overridable so the transport itself can be
        #: driven against a local stub in tests - without that seam the
        #: only way to cover this class is to re-implement it in the test,
        #: which covers the copy and not the code.
        self._base_url = (base_url or f"https://{host}").rstrip("/")
        self._timeout = timeout or settings.KONE_API_TIMEOUT_SECONDS
        #: scope-set -> (token, expires_at_epoch)
        self._tokens: Dict[str, tuple[str, float]] = {}

    @property
    def source(self) -> str:
        return "kone-api"

    @property
    def _token_url(self) -> str:
        return f"{self._base_url}/api/v2/oauth2/token"

    def _fetch_token(self, scopes: Sequence[str]) -> str:
        key = " ".join(sorted(scopes))
        cached = self._tokens.get(key)
        if cached and cached[1] > time.time():
            return cached[0]

        body = urllib.parse.urlencode(
            {"grant_type": "client_credentials", "scope": " ".join(scopes)}
        ).encode()
        basic = base64.b64encode(
            f"{self._client_id}:{self._client_secret}".encode()
        ).decode()
        request = urllib.request.Request(
            self._token_url,
            data=body,
            headers={
                "Authorization": f"Basic {basic}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:
                payload = json.loads(response.read())
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            raise AdapterError(f"KONE token request failed: {exc}") from exc

        token = payload.get("access_token")
        if not token:
            raise AdapterError("KONE token response carried no access_token")
        # expires_in is seconds; fall back to a conservative 5 minutes.
        ttl = float(payload.get("expires_in") or 300)
        self._tokens[key] = (token, time.time() + ttl - _EXPIRY_SAFETY_MARGIN_SECONDS)
        return token

    def get(self, path: str, scopes: Sequence[str]) -> Any:
        token = self._fetch_token(scopes)
        url = f"{self._base_url}{path}"
        request = urllib.request.Request(
            url, headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:
                return json.loads(response.read())
        except urllib.error.HTTPError as exc:
            # 404 is "this equipment/order does not exist", which is an
            # expected outcome rather than an integration fault - the
            # adapters turn it into None. Everything else is a real failure.
            if exc.code == 404:
                return None
            raise AdapterError(f"KONE GET {path} failed: HTTP {exc.code}") from exc
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            raise AdapterError(f"KONE GET {path} failed: {exc}") from exc


class RecordedKoneApiClient:
    """Replays recorded responses in KONE's real field shapes.

    The fixtures this reads were written from KONE's published TypeScript
    interfaces (``src/common/types.ts`` in the examples repo), field name for
    field name, rather than from the generic shapes this build invented
    before it had seen the API. That is what makes a contract test against
    this client worth anything: it exercises the same mapping code the HTTP
    client would feed, over the same keys the real service returns.

    It is **not** a substitute for one live call. It cannot catch a field
    KONE documents and does not send, a pagination envelope the examples
    omit, or an auth scope that turns out to be insufficient.
    """

    def __init__(self, documents: Optional[Dict[str, Any]] = None) -> None:
        self._documents = documents if documents is not None else _load_recorded()

    @property
    def source(self) -> str:
        return "fixture"

    def get(self, path: str, scopes: Sequence[str]) -> Any:  # noqa: ARG002 - parity
        return self._documents.get(path)


def _load_recorded() -> Dict[str, Any]:
    with open(_FIXTURES_DIR / "kone_api_responses.json", encoding="utf-8") as handle:
        return json.load(handle)


def build_client() -> KoneApiClient:
    """The configured client: real when credentials exist, recorded otherwise."""
    if settings.kone_api_configured:
        return HttpKoneApiClient(settings.KONE_CLIENT_ID, settings.KONE_CLIENT_SECRET)
    return RecordedKoneApiClient()


# --------------------------------------------------------------------------
# Paths, from the examples repo. Kept here so no caller builds a URL itself.
# --------------------------------------------------------------------------
def service_orders_path(ken: str) -> str:
    return f"/api/v2/equipment/{normalise_ken(ken)}/serviceOrders"


def service_order_path(ken: str, service_order_id: str) -> str:
    return f"/api/v2/equipment/{normalise_ken(ken)}/serviceOrders/{service_order_id}"


def equipment_search_path(endpoint: str) -> str:
    """Equipment Status API 2.0 shares one base for availability/status/movement."""
    return f"/api/v2/equipment/search/{endpoint}"


def available_products() -> List[str]:
    """Which KONE products this integration speaks to.

    Spare-parts inventory is deliberately absent: KONE publishes no
    spare-parts API in its reference implementation, so the spare-parts
    adapter has no real backend to point at and stays fixture-only. Listing
    it here would imply an integration that does not exist.
    """
    return ["service-info-v2", "equipment-status-v2"]
