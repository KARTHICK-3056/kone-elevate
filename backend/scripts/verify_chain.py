#!/usr/bin/env python
"""Verify the audit chain and alert on a break. Meant to run on a schedule.

Run:
    python scripts/verify_chain.py
    python scripts/verify_chain.py --json

Exit code: 1 when the chain is broken, 0 when it verifies clean - so this is
cron/CI-alerting-ready as-is, the same convention scripts/check_drift.py and
scripts/anchor_chain_head.py already use. Configure
CHAIN_VERIFY_ALERT_WEBHOOK_URL to also POST a JSON payload to a paging
system when the chain is broken; with it unset, a break is still printed and
still exits 1 - alerting is additive, not a prerequisite for detection.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.alerting import post_alert  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.core.database import SessionLocal  # noqa: E402
from app.core.metrics import record_chain_verification  # noqa: E402
from app.services import audit_service  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Print the full result as JSON")
    args = parser.parse_args()

    with SessionLocal() as session:
        result = audit_service.verify_chain(session)

    record_chain_verification(bool(result["valid"]))

    if args.json:
        print(json.dumps(result, indent=2, default=str))
    else:
        print("=" * 70)
        print("AUDIT CHAIN VERIFICATION")
        print("=" * 70)
        print(f"  records checked : {result['records_checked']}")
        print(f"  valid           : {result['valid']}")
        if not result["valid"]:
            print(f"  invalid_record  : {result.get('invalid_record')}")
            print(f"  reason          : {result.get('reason')}")
            print(f"  message         : {result.get('message')}")

    if result["valid"]:
        return 0

    alerted = post_alert(
        settings.CHAIN_VERIFY_ALERT_WEBHOOK_URL,
        {
            "system": settings.APP_NAME,
            "alert": "audit_chain_verification_failed",
            "invalid_record": result.get("invalid_record"),
            "reason": result.get("reason"),
            "message": result.get("message"),
        },
    )
    if settings.CHAIN_VERIFY_ALERT_WEBHOOK_URL and not alerted:
        print("  ! CHAIN_VERIFY_ALERT_WEBHOOK_URL is set but the POST failed - see stderr above.")
    elif not settings.CHAIN_VERIFY_ALERT_WEBHOOK_URL:
        print("  (CHAIN_VERIFY_ALERT_WEBHOOK_URL is not set - printed here only, nobody was paged.)")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
