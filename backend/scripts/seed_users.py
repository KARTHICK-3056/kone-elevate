#!/usr/bin/env python
"""Provision the five demo accounts, one per role.

Run:
    python scripts/seed_users.py
    python scripts/seed_users.py --reset          # recreate all demo accounts
    python scripts/seed_users.py --password "..."  # set one shared password

Why a script and not a signup page
----------------------------------
There is deliberately no public registration endpoint. An endpoint that lets
a caller choose their own role is a privilege-escalation hole wearing a
registration form, so accounts are provisioned - by a supervisor through
``POST /api/v1/auth/users``, or out of band by this script. That leaves the
usual bootstrapping question ("who creates the first supervisor?"), answered
the same way this project already answers it for demo components: an
operator with direct database access runs a seed script.

These are demo credentials for a prototype. They are printed to the terminal
on purpose so an evaluator can sign in immediately. Do not use this script,
or these passwords, anywhere real.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.database import SessionLocal, create_all  # noqa: E402
from app.services import auth_service  # noqa: E402
from app.services.auth_service import DuplicateUserError  # noqa: E402
from app.utils.enums import Role  # noqa: E402

DEFAULT_PASSWORD = "elevate-demo-2026"

DEMO_USERS = [
    {
        "email": "technician@kone-elevate.demo",
        "display_name": "R. Karthik",
        "role": Role.TECHNICIAN.value,
        "country": "India",
        "frontline_unit": "Chennai",
        "does": "Registers components, logs service events, runs AI assessments.",
    },
    {
        "email": "supervisor@kone-elevate.demo",
        "display_name": "S. Meenakshi",
        "role": Role.SUPERVISOR.value,
        "country": "India",
        "frontline_unit": "Chennai",
        "does": "Everything a technician can do, plus provisioning accounts.",
    },
    {
        "email": "planner@kone-elevate.demo",
        "display_name": "A. Ramesh",
        "role": Role.RECOVERY_PLANNER.value,
        "country": "India",
        "frontline_unit": "Bengaluru",
        "does": (
            "Runs component-recovery capacity planning and the end-of-life forecast. "
            "A different frontline unit from the technician/supervisor on "
            "purpose, so the demo shows the ?all_units=true override actually "
            "doing something."
        ),
    },
    {
        "email": "sustainability@kone-elevate.demo",
        "display_name": "P. Lakshmi",
        "role": Role.SUSTAINABILITY_CONTROLLER.value,
        "country": None,
        "frontline_unit": None,
        "does": (
            "Owns ESRS/BRSR reporting and anchors the audit chain. Global role - "
            "no country of its own, because a fleet-wide disclosure scoped to "
            "one country would not be a fleet-wide disclosure."
        ),
    },
    {
        "email": "auditor@kone-elevate.demo",
        "display_name": "D. Fernandes",
        "role": Role.READ_ONLY_AUDITOR.value,
        "country": None,
        "frontline_unit": None,
        "does": "Sees every record and the audit chain, across every country. Cannot change anything.",
    },
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--password",
        default=DEFAULT_PASSWORD,
        help=f"Shared demo password (default: {DEFAULT_PASSWORD})",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete and recreate the demo accounts if they already exist.",
    )
    args = parser.parse_args()

    if len(args.password) < 12:
        print("Password must be at least 12 characters.", file=sys.stderr)
        return 2

    create_all()

    created, skipped = [], []
    with SessionLocal() as db:
        for spec in DEMO_USERS:
            existing = auth_service.get_by_email(db, spec["email"])
            if existing is not None:
                if not args.reset:
                    skipped.append(spec)
                    continue
                db.delete(existing)
                db.flush()
            try:
                auth_service.create_user(
                    db,
                    email=spec["email"],
                    password=args.password,
                    display_name=spec["display_name"],
                    role=spec["role"],
                    country=spec.get("country"),
                    frontline_unit=spec.get("frontline_unit"),
                    commit=False,
                )
            except DuplicateUserError:  # pragma: no cover - guarded above
                skipped.append(spec)
                continue
            created.append(spec)
        db.commit()

    width = 70
    print("=" * width)
    print("DEMO ACCOUNTS")
    print("=" * width)
    for spec in DEMO_USERS:
        state = "created" if spec in created else "already existed"
        print(f"\n  {spec['role']}  ({state})")
        print(f"    email    : {spec['email']}")
        print(f"    password : {args.password}")
        print(f"    name     : {spec['display_name']}")
        tenant = (
            f"{spec['frontline_unit']}, {spec['country']}" if spec.get("country") else "global (no country)"
        )
        print(f"    tenant   : {tenant}")
        print(f"    can      : {spec['does']}")

    print()
    print("=" * width)
    print(f"{len(created)} created, {len(skipped)} already existed.")
    if skipped and not args.reset:
        print("Re-run with --reset to recreate existing accounts with a new password.")
    print()
    print("These are PROTOTYPE demo credentials, printed deliberately so an")
    print("evaluator can sign in. They are not fit for any real deployment.")
    print("=" * width)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
