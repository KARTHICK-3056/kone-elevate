"""Publish the audit-chain head hash so tamper evidence survives a DBA.

Run:
    python scripts/anchor_chain_head.py
    python scripts/anchor_chain_head.py --date 2026-09-12
    python scripts/anchor_chain_head.py --check

What this is for
----------------
``verify_chain`` detects a record edited in place. It cannot detect an
administrator who deletes a record and re-hashes everything after it: the
rebuilt chain verifies perfectly, because the database is the only witness.

Publishing each day's head hash somewhere outside the database adds a second
witness. Any later rewrite of history before that day produces a head that no
longer matches the published value.

Scheduling
----------
Run once daily (cron / Task Scheduler / a scheduled CI workflow). Exit code 1
means the anchor has no external witness - so scheduling this with alerting on
a non-zero exit tells you the protection is not actually in place, which is
the honest default until CHAIN_ANCHOR_WEBHOOK_URL is configured.

The external store
------------------
Set ``CHAIN_ANCHOR_WEBHOOK_URL`` to an append-only endpoint outside this
system's administrative control - a separate logging account, a transparency
log, a notary service, or a public blockchain. Without it, anchors are written
to this database and a local file, both of which the same administrator can
rewrite. That configuration is reported, never assumed away.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import settings  # noqa: E402
from app.core.database import SessionLocal  # noqa: E402
from app.services import anchor_service, audit_service  # noqa: E402


def _publish_externally(payload: dict) -> tuple[str | None, str | None]:
    """POST the anchor to the configured external store.

    Returns ``(published_to, receipt)``. A failure is reported, never
    swallowed: an anchor wrongly recorded as externally witnessed is worse
    than no anchor at all.
    """
    url = settings.CHAIN_ANCHOR_WEBHOOK_URL.strip()
    if not url:
        return None, None

    import urllib.error
    import urllib.request

    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            receipt = response.read().decode("utf-8", errors="replace")[:500]
            return url, receipt
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        print(f"  ! external publication FAILED: {exc}", file=sys.stderr)
        return None, None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", help="Anchor date (YYYY-MM-DD). Defaults to today.")
    parser.add_argument(
        "--check", action="store_true", help="Report anchoring status without writing."
    )
    args = parser.parse_args()

    with SessionLocal() as session:
        if args.check:
            status = anchor_service.anchor_status(session)
            print(json.dumps(status, indent=2, default=str))
            return 0 if status["externally_witnessed_anchors"] else 1

        anchor_date = date.fromisoformat(args.date) if args.date else None
        head_hash = audit_service.latest_hash(session)

        published_to, receipt = _publish_externally(
            {
                "anchor_date": (anchor_date or date.today()).isoformat(),
                "head_hash": head_hash,
                "system": settings.APP_NAME,
            }
        )

        anchor = anchor_service.create_anchor(
            session,
            anchor_date=anchor_date,
            actor="anchor-script",
            published_to=published_to,
            external_receipt=receipt,
        )
        if anchor is None:
            print("Audit chain is empty - nothing to anchor.")
            return 0

        status = anchor_service.anchor_status(session)

    print("=" * 70)
    print("AUDIT CHAIN ANCHOR")
    print("=" * 70)
    print(f"  date          : {anchor.anchor_date}")
    print(f"  head hash     : {anchor.head_hash}")
    print(f"  records       : {anchor.record_count}")
    print(f"  local log     : {anchor_service.anchor_log_path()}")
    print(f"  published to  : {anchor.published_to or 'NOWHERE (local only)'}")
    print()
    print(f"  {status['protection']}")
    print()

    if not anchor.published_to:
        print("Publish this line to an append-only store outside this system:")
        print(f"  {anchor.anchor_date.isoformat()} {anchor.head_hash}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
