"""Secrets resolution: environment variables by default, HashiCorp Vault
when configured.

Honest scope
------------
This build has no live Vault server to run against - the P4 finding is
that the shipped defaults (``dev-only-insecure-key-change-me``,
``change_me``) are exactly what a real deployment is left holding if
nothing better is wired in, which is a genuine gap regardless of whether a
Vault instance happens to be available in this environment.
:class:`VaultSecretsProvider` is written against Vault's documented KV v2
HTTP API and unit-tested against a mocked response
(``tests/test_secrets.py``) - real usage still needs an operator to point
``VAULT_ADDR``/``VAULT_TOKEN`` at an actual instance and confirm the round
trip once, the same way ``docs/threat-model.md`` records as still open.

Only ``SECRET_KEY`` and the SMTP credentials are sourced this way today
(see ``apply_vault_overrides`` in ``app.core.config``) - ``DATABASE_URL``
embeds its credential inside a connection string rather than as a standalone
value, so vaulting it needs URL reconstruction this pass did not do; that
gap is recorded rather than silently left, in the same place.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from typing import Optional, Protocol


class SecretsProvider(Protocol):
    def get(self, key: str, default: str = "") -> str: ...


class EnvSecretsProvider:
    """The status quo: read straight from the process environment."""

    def get(self, key: str, default: str = "") -> str:
        return os.environ.get(key, default)


class VaultSecretsProvider:
    """Reads secrets from a single KV v2 path in HashiCorp Vault.

    One path holds every secret this application needs (e.g.
    ``secret/data/kone-elevate`` with keys ``SECRET_KEY``,
    ``SMTP_PASSWORD``, ...) rather than one Vault path per key - simpler to
    provision and rotate together, and matches how the values already
    travel together in ``.env``.
    """

    def __init__(self, addr: str, token: str, mount: str, path: str, timeout: int = 5) -> None:
        self._url = f"{addr.rstrip('/')}/v1/{mount.strip('/')}/data/{path.strip('/')}"
        self._token = token
        self._timeout = timeout
        self._cache: Optional[dict] = None

    def _fetch(self) -> dict:
        if self._cache is not None:
            return self._cache
        request = urllib.request.Request(self._url, headers={"X-Vault-Token": self._token})
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:
                payload = json.loads(response.read())
            self._cache = payload["data"]["data"]
        except (urllib.error.URLError, TimeoutError, OSError, KeyError, ValueError) as exc:
            print(f"! Vault secrets fetch failed ({exc}); falling back to environment.", file=sys.stderr)
            self._cache = {}
        return self._cache

    def get(self, key: str, default: str = "") -> str:
        value = self._fetch().get(key)
        return str(value) if value is not None else os.environ.get(key, default)


def get_secrets_provider() -> SecretsProvider:
    """``VAULT_ADDR`` + ``VAULT_TOKEN`` set -> Vault; otherwise the environment.

    Neither is read through ``app.core.config.Settings`` - this has to
    resolve *before* ``Settings`` is fully constructed, since its result
    overrides some of that construction (see ``apply_vault_overrides``).
    """
    addr = os.environ.get("VAULT_ADDR", "").strip()
    token = os.environ.get("VAULT_TOKEN", "").strip()
    if addr and token:
        mount = os.environ.get("VAULT_KV_MOUNT", "secret").strip()
        path = os.environ.get("VAULT_KV_PATH", "kone-elevate").strip()
        return VaultSecretsProvider(addr, token, mount, path)
    return EnvSecretsProvider()
