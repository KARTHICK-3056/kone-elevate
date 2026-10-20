"""P6: workshop outcome capture, shadow-mode predictions, trust ratings.

Adds:
* ``recovery_items.workshop_outcome`` / ``survived_in_service`` /
  ``outcome_notes`` / ``outcome_recorded_at`` / ``outcome_recorded_by`` -
  the one-tap outcome capture the pilot's real-label training set depends on.
* ``predictions.shadow`` - marks an assessment as shadow-mode (computed and
  stored, never surfaced - see app.services.prediction_service).
* ``predictions.technician_trust_rating`` - the one pilot metric that
  cannot be derived from data already recorded elsewhere.

Revision ID: 0012_p6_outcome_and_shadow
Revises: 0011_cached_recommendation
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0012_p6_outcome_and_shadow'
down_revision: Union[str, None] = '0011_cached_recommendation'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('recovery_items', schema=None) as batch_op:
        batch_op.add_column(sa.Column('workshop_outcome', sa.String(length=32), nullable=True))
        batch_op.add_column(sa.Column('survived_in_service', sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column('outcome_notes', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('outcome_recorded_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('outcome_recorded_by', sa.String(length=96), nullable=True))
        batch_op.create_index('ix_recovery_items_workshop_outcome', ['workshop_outcome'])

    with op.batch_alter_table('predictions', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('shadow', sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch_op.add_column(sa.Column('technician_trust_rating', sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('predictions', schema=None) as batch_op:
        batch_op.drop_column('technician_trust_rating')
        batch_op.drop_column('shadow')

    with op.batch_alter_table('recovery_items', schema=None) as batch_op:
        batch_op.drop_index('ix_recovery_items_workshop_outcome')
        batch_op.drop_column('outcome_recorded_by')
        batch_op.drop_column('outcome_recorded_at')
        batch_op.drop_column('outcome_notes')
        batch_op.drop_column('survived_in_service')
        batch_op.drop_column('workshop_outcome')
