"""Row-level multi-tenancy: country and frontline-unit scope.

Adds ``country``/``frontline_unit`` to ``users`` and ``components``, and
``country`` alone to ``recovery_items`` and ``service_demands`` - the
Recovery Exchange is deliberately not scoped by frontline unit, since
routing recovered stock across branches within one country is the point of
it. See ``app.core.tenancy`` for the enforcement side.

Existing rows backfill to NULL, which for a non-global role means "sees
nothing until assigned a tenant" rather than falling open to "sees
everything" - the safe failure direction for a security boundary. Demo data
is re-seeded with real values by ``scripts/seed_database.py`` /
``scripts/seed_users.py``.

Revision ID: 0009_tenancy
Revises: 0008_email_verification
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0009_tenancy'
down_revision: Union[str, None] = '0008_email_verification'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('country', sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column('frontline_unit', sa.String(length=96), nullable=True))
        batch_op.create_index('ix_users_country', ['country'])
        batch_op.create_index('ix_users_frontline_unit', ['frontline_unit'])

    with op.batch_alter_table('components', schema=None) as batch_op:
        batch_op.add_column(sa.Column('country', sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column('frontline_unit', sa.String(length=96), nullable=True))
        batch_op.create_index('ix_components_country', ['country'])
        batch_op.create_index('ix_components_frontline_unit', ['frontline_unit'])
        batch_op.create_index('ix_components_country_unit', ['country', 'frontline_unit'])

    with op.batch_alter_table('recovery_items', schema=None) as batch_op:
        batch_op.add_column(sa.Column('country', sa.String(length=64), nullable=True))
        batch_op.create_index('ix_recovery_items_country', ['country'])

    with op.batch_alter_table('service_demands', schema=None) as batch_op:
        batch_op.add_column(sa.Column('country', sa.String(length=64), nullable=True))
        batch_op.create_index('ix_service_demands_country', ['country'])

    # Best-effort backfill for existing recovery items from their component,
    # so upgrading a running deployment does not silently hide already-listed
    # stock from every non-global role.
    op.execute(
        """
        UPDATE recovery_items
        SET country = (
            SELECT components.country FROM components WHERE components.id = recovery_items.component_id
        )
        """
    )


def downgrade() -> None:
    with op.batch_alter_table('service_demands', schema=None) as batch_op:
        batch_op.drop_index('ix_service_demands_country')
        batch_op.drop_column('country')

    with op.batch_alter_table('recovery_items', schema=None) as batch_op:
        batch_op.drop_index('ix_recovery_items_country')
        batch_op.drop_column('country')

    with op.batch_alter_table('components', schema=None) as batch_op:
        batch_op.drop_index('ix_components_country_unit')
        batch_op.drop_index('ix_components_frontline_unit')
        batch_op.drop_index('ix_components_country')
        batch_op.drop_column('frontline_unit')
        batch_op.drop_column('country')

    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_index('ix_users_frontline_unit')
        batch_op.drop_index('ix_users_country')
        batch_op.drop_column('frontline_unit')
        batch_op.drop_column('country')
