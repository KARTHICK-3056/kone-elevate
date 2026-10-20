"""Shared webhook-POST helper for scheduled/cron alerting scripts.

Extracted from the pattern ``scripts/anchor_chain_head.py`` already used for
publishing the chain anchor externally, so drift alerts
(``scripts/check_drift.py``) and chain-verification-failure alerts
(``scripts/verify_chain.py``) don't each reimplement it. An alert is
best-effort by design: a failed webhook POST is logged to stderr, never
raised, because a paging system being briefly unreachable must not crash
the check that was trying to page it.
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from typing import Any, Dict


def post_alert(url: str, payload: Dict[str, Any], timeout: int = 15) -> bool:
    """POST a JSON payload to an alert webhook. Returns whether it succeeded.

    A no-op (returns False) when ``url`` is empty - callers should already
    be checking this, but making the empty case cheap and safe means a
    caller can pass a possibly-empty config value straight through.
    """
    if not url.strip():
        return False

    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout):
            return True
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        print(f"  ! alert webhook POST failed: {exc}", file=sys.stderr)
        return False
