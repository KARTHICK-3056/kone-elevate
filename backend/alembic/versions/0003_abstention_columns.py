"""Widen predictions.recommendation and add abstention columns.

Backs the DEFER_TO_INSPECTION outcome (app.ml.abstention): the recommendation
column was String(16), too narrow for "DEFER_TO_INSPECTION" (20 chars).
Also adds underlying_recommendation (the model's own best guess, retained
even when the surfaced recommendation is DEFER_TO_INSPECTION) and abstained.

Revision ID: 0003_abstention_columns
Revises: 0002_audit_chain_lock
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0003_abstention_columns'
down_revision: Union[str, None] = '0002_audit_chain_lock'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('predictions', schema=None) as batch_op:
        batch_op.alter_column(
            'recommendation', existing_type=sa.String(length=16), type_=sa.String(length=24)
        )
        batch_op.add_column(sa.Column('underlying_recommendation', sa.String(length=24), nullable=True))
        batch_op.add_column(
            sa.Column('abstained', sa.Boolean(), nullable=False, server_default=sa.false())
        )


def downgrade() -> None:
    with op.batch_alter_table('predictions', schema=None) as batch_op:
        batch_op.drop_column('abstained')
        batch_op.drop_column('underlying_recommendation')
        batch_op.alter_column(
            'recommendation', existing_type=sa.String(length=24), type_=sa.String(length=16)
        )
