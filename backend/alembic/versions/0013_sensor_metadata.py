"""Variable sensor metadata on service events (JSONB on PostgreSQL).

Adds ``service_events.sensor_metadata`` - a flat key/value bag for
vendor/sensor-specific readings that do not fit the fixed
operating_hours/vibration/temperature/inspection_score columns (e.g. current
draw, acoustic emission, door-cycle count). Unlike every other JSON column in
this codebase (``predictions.*``, ``audit_logs.data_snapshot``), which stay on
the portable ``JSON`` type, this one is declared with a PostgreSQL JSONB
variant, because the reason for the column is genuinely variable-shape data
per sensor vendor - the case JSONB's indexable storage exists for.

Revision ID: 0013_sensor_metadata
Revises: 0012_p6_outcome_and_shadow

Named ``0013_sensor_metadata`` rather than the longer, more literal
``0013_service_event_sensor_metadata`` because Postgres's
``alembic_version.version_num`` column is ``VARCHAR(32)`` and the longer id
does not fit - discovered by actually running this migration against a real
Postgres instance, not just SQLite (see docs/database-scale.md's own
"tested against real Postgres, not just SQLite" pattern).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = '0013_sensor_metadata'
down_revision: Union[str, None] = '0012_p6_outcome_and_shadow'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('service_events', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                'sensor_metadata',
                sa.JSON().with_variant(postgresql.JSONB(), 'postgresql'),
                nullable=True,
            )
        )


def downgrade() -> None:
    with op.batch_alter_table('service_events', schema=None) as batch_op:
        batch_op.drop_column('sensor_metadata')
