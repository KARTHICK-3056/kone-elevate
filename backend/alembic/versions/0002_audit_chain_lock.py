"""Add audit_chain_lock table.

Backs the fix for the audit-chain fork under concurrent writes (see
app.services.audit_service._acquire_chain_lock and
app.models.audit.AuditChainLock): every append now issues an UPDATE against
this single-row table first, taking a real database write lock that
serialises concurrent appends.

Revision ID: 0002_audit_chain_lock
Revises: 0001_initial
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0002_audit_chain_lock'
down_revision: Union[str, None] = '0001_initial'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'audit_chain_lock',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.bulk_insert(
        sa.table('audit_chain_lock', sa.column('id', sa.Integer()), sa.column('version', sa.Integer())),
        [{'id': 1, 'version': 0}],
    )


def downgrade() -> None:
    op.drop_table('audit_chain_lock')
