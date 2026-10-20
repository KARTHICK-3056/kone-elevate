"""Prototype security helpers.

Scope note (honest disclosure)
------------------------------
This prototype ships a placeholder authentication layer. It provides:

* SHA-256 canonical hashing used by the tamper-evident audit chain,
* PBKDF2-HMAC password hashing (standard library, no extra dependency),
* a very small HMAC-signed token helper used by the optional demo login.

It does NOT implement account management, refresh tokens, RBAC, rate limiting
or session revocation. Do not treat it as production security.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from typing import Any, Dict, Optional

from app.core.config import settings

GENESIS_HASH = "0" * 64


# --------------------------------------------------------------------------
# Canonical hashing (audit chain)
# --------------------------------------------------------------------------
def canonical_json(payload: Any) -> str:
    """Serialise a payload deterministically.

    Keys are sorted and separators fixed so that two logically identical
    payloads always produce byte-identical output - a hard requirement for a
    reproducible hash chain.
    """
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), default=str, ensure_ascii=False
    )


def sha256_hex(text: str) -> str:
    """Return the hex SHA-256 digest of the given text."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def chain_hash(previous_hash: str, record: Dict[str, Any]) -> str:
    """Compute the audit-chain hash for a record linked to previous_hash."""
    return sha256_hex(previous_hash + "|" + canonical_json(record))


# --------------------------------------------------------------------------
# Password hashing (placeholder auth)
# --------------------------------------------------------------------------
def hash_password(
    password: str, salt: Optional[str] = None, rounds: Optional[int] = None
) -> str:
    """Hash a password with PBKDF2-HMAC-SHA256.

    Stored format: ``pbkdf2$<rounds>$<salt-hex>$<digest-hex>``. The round
    count is stored *inside* the hash, so raising the work factor later does
    not invalidate existing passwords - :func:`verify_password` reads the
    rounds each hash was created with.
    """
    salt = salt or secrets.token_hex(16)
    rounds = rounds or settings.PBKDF2_ROUNDS
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), rounds)
    return "pbkdf2$" + str(rounds) + "$" + salt + "$" + digest.hex()


def verify_password(password: str, stored: str) -> bool:
    """Constant-time verification of a password against a stored hash."""
    try:
        scheme, rounds, salt, expected = stored.split("$")
        if scheme != "pbkdf2":
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), bytes.fromhex(salt), int(rounds)
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(digest.hex(), expected)


# --------------------------------------------------------------------------
# Minimal signed tokens (placeholder auth)
# --------------------------------------------------------------------------
def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def create_access_token(
    subject: str, role: str = "engineer", expires_minutes: Optional[int] = None
) -> str:
    """Create a compact HMAC-signed token (JWT-like, deliberately minimal)."""
    expires_minutes = expires_minutes or settings.ACCESS_TOKEN_EXPIRE_MINUTES
    payload = {"sub": subject, "role": role, "exp": int(time.time()) + expires_minutes * 60}
    body = _b64(canonical_json(payload).encode())
    signature = _b64(
        hmac.new(settings.SECRET_KEY.encode(), body.encode(), hashlib.sha256).digest()
    )
    return body + "." + signature


def decode_access_token(token: str) -> Optional[Dict[str, Any]]:
    """Return the token payload if the signature is valid and unexpired."""
    try:
        body, signature = token.split(".")
    except ValueError:
        return None
    expected = _b64(
        hmac.new(settings.SECRET_KEY.encode(), body.encode(), hashlib.sha256).digest()
    )
    if not hmac.compare_digest(signature, expected):
        return None
    payload = json.loads(_unb64(body))
    if payload.get("exp", 0) < time.time():
        return None
    return payload
