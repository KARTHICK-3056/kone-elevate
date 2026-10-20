"""Remove the Recovery Exchange.

The exchange (recovered-parts listings, service demands and scored matches)
was removed from the platform. This drops its three tables and moves any
component still sitting in an exchange state (``AVAILABLE``, ``ALLOCATED``,
``PARTS_FITTED``) to ``PART_RECOVERY`` - its usable sub-components are being
recovered, which is what all three meant for the component itself. No
material-flow row is written: both sides are the same E5-5 outflow route,
so nothing crosses the reporting boundary.

``audit_logs`` and the ``material_flow`` ledger are untouched: they record
what happened at the time, including exchange activity.

The downgrade recreates the three tables empty; the listings, demands and
matches themselves are not recoverable.

``apply(connection)`` is also used by ``scripts/migrate_dev_db.py``
for the local SQLite database, which is created by ``create_all`` rather than
by Alembic.

Revision ID: 0019_remove_recovery_exchange
Revises: 0018_recommendation_categories
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0019_remove_recovery_exchange'
down_revision: Union[str, None] = '0018_recommendation_categories'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


EXCHANGE_STATES = ('AVAILABLE', 'ALLOCATED', 'PARTS_FITTED')
#: Child tables first, so foreign keys never block a drop.
TABLES = ('recovery_matches', 'recovery_items', 'service_demands')


def apply(connection) -> None:
    """Move components out of exchange states and drop the exchange tables."""
    for state in EXCHANGE_STATES:
        connection.execute(
            sa.text("UPDATE components SET current_status = 'PART_RECOVERY' WHERE current_status = :state"),
            {'state': state},
        )
    existing = set(sa.inspect(connection).get_table_names())
    for table in TABLES:
        if table in existing:
            connection.execute(sa.text(f'DROP TABLE {table}'))


def upgrade() -> None:
    apply(op.get_bind())


def downgrade() -> None:
    op.create_table(
        'service_demands',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('reference', sa.String(length=48), nullable=False),
        sa.Column('required_component_type', sa.String(length=48), nullable=False),
        sa.Column('required_material', sa.String(length=32), nullable=True),
        sa.Column('minimum_condition', sa.String(length=24), nullable=False),
        sa.Column('location', sa.String(length=96), nullable=True),
        sa.Column('estimated_value', sa.Float(), nullable=False),
        sa.Column('priority', sa.String(length=16), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('required_by', sa.Date(), nullable=True),
        sa.Column('requested_by', sa.String(length=96), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('country', sa.String(length=64), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_service_demands_reference', 'service_demands', ['reference'], unique=True)
    op.create_index('ix_service_demands_country', 'service_demands', ['country'])
    op.create_index('ix_service_demands_type_status', 'service_demands', ['required_component_type', 'status'])

    op.create_table(
        'recovery_items',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('component_id', sa.Integer(), nullable=False),
        sa.Column('condition', sa.String(length=24), nullable=False),
        sa.Column('availability_status', sa.String(length=24), nullable=False),
        sa.Column('estimated_value', sa.Float(), nullable=False),
        sa.Column('estimated_co2_saving', sa.Float(), nullable=False),
        sa.Column('location', sa.String(length=96), nullable=True),
        sa.Column('available_from', sa.Date(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('country', sa.String(length=64), nullable=True),
        sa.Column('workshop_outcome', sa.String(length=32), nullable=True),
        sa.Column('survived_in_service', sa.Boolean(), nullable=True),
        sa.Column('outcome_notes', sa.Text(), nullable=True),
        sa.Column('outcome_recorded_at', sa.DateTime(), nullable=True),
        sa.Column('outcome_recorded_by', sa.String(length=96), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['component_id'], ['components.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_recovery_items_component_id', 'recovery_items', ['component_id'])
    op.create_index('ix_recovery_items_country', 'recovery_items', ['country'])
    op.create_index('ix_recovery_items_status_condition', 'recovery_items', ['availability_status', 'condition'])

    op.create_table(
        'recovery_matches',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('recovery_item_id', sa.Integer(), nullable=False),
        sa.Column('service_demand_id', sa.Integer(), nullable=False),
        sa.Column('match_score', sa.Float(), nullable=False),
        sa.Column('reason', sa.JSON(), nullable=True),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('decided_by', sa.String(length=96), nullable=True),
        sa.Column('decided_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['recovery_item_id'], ['recovery_items.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['service_demand_id'], ['service_demands.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_recovery_matches_pair', 'recovery_matches', ['recovery_item_id', 'service_demand_id'], unique=True)
