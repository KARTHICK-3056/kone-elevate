"""Tie each assessment to the life of the component it describes.

Adds ``predictions.life_cycle_number``. Found while reviewing CE-1: once a
component could be refitted, its pre-recovery assessment stayed its
``latest_prediction``. A part recovered on a DISPOSE verdict, refurbished
and refitted still read DISPOSE on its passport, and
``forecast_service.split_fleet`` filed it as refurbishment backlog the
instant it re-entered service - the capacity planner queueing labour hours
for a component that had just been installed.

Existing rows default to 1 and every existing component is on life 1, so
the filter added alongside this migration is a no-op for historical data.

Revision ID: 0015_prediction_life
Revises: 0014_life_cycle_number
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0015_prediction_life'
down_revision: Union[str, None] = '0014_life_cycle_number'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('predictions', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                'life_cycle_number',
                sa.Integer(),
                nullable=False,
                server_default='1',
            )
        )


def downgrade() -> None:
    with op.batch_alter_table('predictions', schema=None) as batch_op:
        batch_op.drop_column('life_cycle_number')
