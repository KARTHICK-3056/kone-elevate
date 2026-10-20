"""Count how many times a component has been put into service.

Adds ``components.life_cycle_number``, the counter that makes a closed
loop observable. Before this, ``ALLOCATED`` was a terminal lifecycle state
and a recovered part never re-entered service, so a second life was
neither reachable nor countable.

Existing rows default to 1: every component already in the database was
installed new exactly once as far as this system can know, and claiming
otherwise retrospectively would invent circularity that never happened.

Revision ID: 0014_life_cycle_number
Revises: 0013_sensor_metadata
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0014_life_cycle_number'
down_revision: Union[str, None] = '0013_sensor_metadata'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('components', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                'life_cycle_number',
                sa.Integer(),
                nullable=False,
                server_default='1',
            )
        )


def downgrade() -> None:
    with op.batch_alter_table('components', schema=None) as batch_op:
        batch_op.drop_column('life_cycle_number')
