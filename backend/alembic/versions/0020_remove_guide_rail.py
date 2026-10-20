"""Remove the Guide Rail component type.

Guide Rail was removed from the platform's component types, training data and
model. This deletes the Guide Rail component records and the rows that hang
off them (predictions, service events, saved simulation scenarios, telemetry
readings), exactly as deleting a component through the API does.

Kept on purpose:

* ``audit_logs`` - hash-chained; it keeps what was recorded.
* ``material_flow`` - the ESRS ledger must outlive the component row, so its
  rows stay (their ``component_pk`` is cleared, as the foreign key's
  ``ON DELETE SET NULL`` does).

The downgrade cannot restore deleted records.

``apply(connection)`` is also used by ``scripts/migrate_dev_db.py`` for the
local SQLite database, which is created by ``create_all`` rather than by
Alembic.

Revision ID: 0020_remove_guide_rail
Revises: 0019_remove_recovery_exchange
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0020_remove_guide_rail'
down_revision: Union[str, None] = '0019_remove_recovery_exchange'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


REMOVED_TYPE = 'Guide Rail'
#: Child tables, deleted first so no foreign key blocks the component delete
#: (SQLite does not enforce ON DELETE CASCADE unless foreign keys are on).
CHILD_TABLES = ('predictions', 'service_events', 'simulation_scenarios', 'telemetry_readings')


def apply(connection) -> int:
    """Delete Guide Rail components and their dependent rows. Returns the count."""
    existing = set(sa.inspect(connection).get_table_names())
    ids = [
        row[0]
        for row in connection.execute(
            sa.text('SELECT id FROM components WHERE component_type = :type'), {'type': REMOVED_TYPE}
        )
    ]
    if not ids:
        return 0
    for table in CHILD_TABLES:
        if table in existing:
            connection.execute(
                sa.text(f'DELETE FROM {table} WHERE component_id IN (SELECT id FROM components WHERE component_type = :type)'),
                {'type': REMOVED_TYPE},
            )
    if 'material_flow' in existing:
        connection.execute(
            sa.text('UPDATE material_flow SET component_pk = NULL WHERE component_pk IN (SELECT id FROM components WHERE component_type = :type)'),
            {'type': REMOVED_TYPE},
        )
    connection.execute(sa.text('DELETE FROM components WHERE component_type = :type'), {'type': REMOVED_TYPE})
    return len(ids)


def upgrade() -> None:
    apply(op.get_bind())


def downgrade() -> None:
    # Deleted records cannot be restored; the type itself returns with the code.
    pass
