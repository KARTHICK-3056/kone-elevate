"""app.core.secrets: env-vs-Vault provider selection and the Vault KV v2 parse.

No live Vault server is available in this environment (see the module
docstring in app.core.secrets), so VaultSecretsProvider is exercised here
against a mocked HTTP response shaped like Vault's documented KV v2 payload,
not a real instance. That is a real, disclosed limit on this coverage, not
a substitute for confirming the round trip against an actual Vault server
before relying on it.
"""

from __future__ import annotations

import json
from unittest.mock import patch

from app.core.secrets import EnvSecretsProvider, VaultSecretsProvider, get_secrets_provider


def test_defaults_to_env_provider_with_no_vault_config(monkeypatch):
    monkeypatch.delenv("VAULT_ADDR", raising=False)
    monkeypatch.delenv("VAULT_TOKEN", raising=False)
    assert isinstance(get_secrets_provider(), EnvSecretsProvider)


def test_selects_vault_provider_when_both_are_set(monkeypatch):
    monkeypatch.setenv("VAULT_ADDR", "http://vault.local:8200")
    monkeypatch.setenv("VAULT_TOKEN", "s.faketoken")
    assert isinstance(get_secrets_provider(), VaultSecretsProvider)


def test_env_provider_reads_the_process_environment(monkeypatch):
    monkeypatch.setenv("SOME_TEST_SECRET", "value-from-env")
    assert EnvSecretsProvider().get("SOME_TEST_SECRET") == "value-from-env"
    assert EnvSecretsProvider().get("MISSING_KEY", "fallback") == "fallback"


class _FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._body = json.dumps(payload).encode()

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *exc) -> None:
        return None


def test_vault_provider_parses_kv2_response():
    kv2_payload = {"data": {"data": {"SECRET_KEY": "vaulted-secret-value"}, "metadata": {}}}
    provider = VaultSecretsProvider("http://vault.local:8200", "s.token", "secret", "kone-elevate")

    with patch("urllib.request.urlopen", return_value=_FakeResponse(kv2_payload)):
        assert provider.get("SECRET_KEY") == "vaulted-secret-value"
        # Cached: a second call must not hit the fake transport again.
        assert provider.get("SECRET_KEY") == "vaulted-secret-value"


def test_vault_provider_falls_back_on_missing_key():
    provider = VaultSecretsProvider("http://vault.local:8200", "s.token", "secret", "kone-elevate")
    with patch("urllib.request.urlopen", return_value=_FakeResponse({"data": {"data": {}}})):
        assert provider.get("NOT_PRESENT", "fallback-value") == "fallback-value"


def test_vault_provider_falls_back_when_unreachable():
    import urllib.error

    provider = VaultSecretsProvider("http://vault.local:8200", "s.token", "secret", "kone-elevate")
    with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("connection refused")):
        assert provider.get("SECRET_KEY", "fallback-value") == "fallback-value"
