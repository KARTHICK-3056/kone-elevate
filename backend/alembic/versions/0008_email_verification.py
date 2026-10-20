"""Self-service signup with emailed one-time codes.

Adds ``users.email_verified`` and the ``email_verifications`` table.

``email_verified`` is separate from ``is_active`` on purpose: "never finished
signing up" and "switched off by a supervisor" both block sign-in, but they
are different states and conflating them makes it impossible to tell which
one an account is in. Existing rows are backfilled to verified - every
account that existed before self-signup was provisioned by a supervisor or
the seed script, and had nothing to prove by email.

Only the SHA-256 of a code is stored, so a database dump yields no usable
codes.

Revision ID: 0008_email_verification
Revises: 0007_users
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0008_email_verification'
down_revision: Union[str, None] = '0007_users'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                'email_verified', sa.Boolean(), nullable=False, server_default=sa.false()
            )
        )

    # Everything that already exists was provisioned out of band.
    # TRUE/FALSE, not 1/0: SQLite accepts both, but Postgres's real boolean
    # column type rejects an integer literal outright (DatatypeMismatch) -
    # this migration had never actually been run against Postgres before.
    op.execute("UPDATE users SET email_verified = TRUE")

    op.create_table(
        'email_verifications',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('code_hash', sa.String(length=64), nullable=False),
        sa.Column('purpose', sa.String(length=32), nullable=False, server_default='signup'),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('attempts', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('consumed_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_email_verifications_user_id', 'email_verifications', ['user_id'])
    op.create_index(
        'ix_email_verifications_user_purpose', 'email_verifications', ['user_id', 'purpose']
    )


def downgrade() -> None:
    op.drop_index('ix_email_verifications_user_purpose', table_name='email_verifications')
    op.drop_index('ix_email_verifications_user_id', table_name='email_verifications')
    op.drop_table('email_verifications')

    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('email_verified')
