"""Daily audit-chain head anchoring.

The hash chain detects records edited in place; it cannot detect an
administrator rebuilding the chain wholesale. Publishing the daily head hash
to a store outside the database makes such a rewrite detectable. This table
records each commitment and, crucially, whether it was actually published
externally - a local-only anchor is a reminder, not evidence.

Revision ID: 0006_chain_anchors
Revises: 0005_dpp_identity
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0006_chain_anchors'
down_revision: Union[str, None] = '0005_dpp_identity'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'chain_anchors',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('anchor_date', sa.Date(), nullable=False),
        sa.Column('head_hash', sa.String(length=64), nullable=False),
        sa.Column('record_count', sa.Integer(), nullable=False),
        sa.Column('published_to', sa.String(length=256), nullable=True),
        sa.Column('external_receipt', sa.String(length=512), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_chain_anchors_anchor_date', 'chain_anchors', ['anchor_date'], unique=True)


def downgrade() -> None:
    op.drop_index('ix_chain_anchors_anchor_date', table_name='chain_anchors')
    op.drop_table('chain_anchors')
