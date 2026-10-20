#!/usr/bin/env python
"""Bring a local database created by ``create_all`` up to date.

The SQLite development database (``kone_elevate.db``) is built by
``create_all``, not Alembic, so data migrations never run against it. This
applies them, using each migration's own function so the two cannot drift:

* ``0018_recommendation_categories`` - renames stored values to the four
  recommendation categories;
* ``0019_remove_recovery_exchange`` - moves components out of the removed
  exchange states and drops the exchange tables;
* ``0020_remove_guide_rail`` - deletes Guide Rail components and their
  dependent rows (the audit chain and material-flow ledger are kept);
* ``0021_remove_control_board`` - the same for Control Board components.

With ``--reassess`` it then re-runs each in-service component's assessment
with the current model, so the cached recommendation comes from the
four-category decision flow rather than from a renamed legacy verdict.

``audit_logs`` is never touched - the chain keeps what was recorded.

Run:
    python scripts/migrate_dev_db.py
    python scripts/migrate_dev_db.py --reassess
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.core.database import SessionLocal, engine  # noqa: E402
from app.models.component import Component  # noqa: E402
from app.services import prediction_service  # noqa: E402
from app.utils.enums import LifecycleStatus  # noqa: E402

VERSIONS = BACKEND / "alembic" / "versions"

#: A part in one of these states is no longer in a device; there is nothing
#: to re-assess.
_NOT_REASSESSED = {
    LifecycleStatus.DISPOSED.value,
    LifecycleStatus.MATERIAL_RECOVERED.value,
}


def _migration(filename: str):
    spec = importlib.util.spec_from_file_location(filename.removesuffix(".py"), VERSIONS / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--reassess", action="store_true", help="Re-run every in-service component's assessment"
    )
    args = parser.parse_args()

    with engine.begin() as connection:
        _migration("0018_recommendation_categories.py").rename_values(connection)
        _migration("0019_remove_recovery_exchange.py").apply(connection)
        removed = _migration("0020_remove_guide_rail.py").apply(connection)
        removed_boards = _migration("0021_remove_control_board.py").apply(connection)
    print("Stored values renamed and the Recovery Exchange tables removed.")
    print(f"Guide Rail components removed: {removed}.")
    print(f"Control Board components removed: {removed_boards}.")

    if not args.reassess:
        return
    db = SessionLocal()
    try:
        counts: dict = {}
        for component in db.query(Component).order_by(Component.id):
            if component.current_status in _NOT_REASSESSED:
                continue
            _, result = prediction_service.assess_component(
                db, component, actor="category-migration", commit=False
            )
            counts[result["recommendation"]] = counts.get(result["recommendation"], 0) + 1
        db.commit()
        for code, count in sorted(counts.items()):
            print(f"    {code:<20} {count:>3}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
