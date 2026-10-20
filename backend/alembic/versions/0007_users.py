"""User accounts for authentication and role-based access control.

Backs the removal of the ``X-Actor`` header path: before this table there was
no such thing as a verified identity, so every entry in the tamper-evident
audit chain was attributed to an unauthenticated string a client chose. The
chain proved only that an unverified claim had not been edited afterwards.

Accounts are provisioned, never self-registered - see app/api/auth.py.

Revision ID: 0007_users
Revises: 0006_chain_anchors
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0007_users'
down_revision: Union[str, None] = '0006_chain_anchors'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'users',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('email', sa.String(length=160), nullable=False),
        sa.Column('display_name', sa.String(length=96), nullable=False),
        sa.Column('password_hash', sa.String(length=160), nullable=False),
        sa.Column('role', sa.String(length=32), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_users_email', 'users', ['email'], unique=True)
    op.create_index('ix_users_role', 'users', ['role'])


def downgrade() -> None:
    op.drop_index('ix_users_role', table_name='users')
    op.drop_index('ix_users_email', table_name='users')
    op.drop_table('users')
