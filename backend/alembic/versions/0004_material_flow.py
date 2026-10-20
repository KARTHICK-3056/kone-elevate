"""Material-flow ledger and per-unit component mass.

Backs ESRS E5-4 / E5-5 disclosure (app.services.material_flow_service). Mass
stops being a read-time configuration lookup and becomes a recorded fact: every
lifecycle transition writes one immutable row stating how many kilograms of
which material crossed the reporting boundary, pinned to the audit-chain entry
that recorded the same transition.

``components.mass_kg`` is the weighed mass of an individual unit. It is
nullable because nothing has been weighed yet; the ledger falls back to the
per-type estimate and flags the row's mass_source accordingly.

Revision ID: 0004_material_flow
Revises: 0003_abstention_columns
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0004_material_flow'
down_revision: Union[str, None] = '0003_abstention_columns'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'material_flow',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('component_pk', sa.Integer(), nullable=True),
        sa.Column('component_id', sa.String(length=48), nullable=False),
        sa.Column('component_type', sa.String(length=48), nullable=False),
        sa.Column('material', sa.String(length=32), nullable=False),
        sa.Column('mass_kg', sa.Float(), nullable=False),
        sa.Column('mass_source', sa.String(length=24), nullable=False),
        sa.Column('from_state', sa.String(length=32), nullable=True),
        sa.Column('to_state', sa.String(length=32), nullable=False),
        sa.Column('direction', sa.String(length=16), nullable=False),
        sa.Column('outflow_route', sa.String(length=32), nullable=True),
        sa.Column('is_secondary', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('flow_date', sa.Date(), nullable=False),
        sa.Column('actor', sa.String(length=96), nullable=False),
        sa.Column('source', sa.String(length=64), nullable=False),
        sa.Column('audit_hash', sa.String(length=64), nullable=True),
        sa.Column('notes', sa.String(length=256), nullable=True),
        sa.Column('recorded_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['component_pk'], ['components.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_material_flow_component_pk', 'material_flow', ['component_pk'])
    op.create_index('ix_material_flow_component_id', 'material_flow', ['component_id'])
    op.create_index('ix_material_flow_component_type', 'material_flow', ['component_type'])
    op.create_index('ix_material_flow_material', 'material_flow', ['material'])
    op.create_index('ix_material_flow_to_state', 'material_flow', ['to_state'])
    op.create_index('ix_material_flow_direction', 'material_flow', ['direction'])
    op.create_index('ix_material_flow_outflow_route', 'material_flow', ['outflow_route'])
    op.create_index('ix_material_flow_flow_date', 'material_flow', ['flow_date'])
    op.create_index('ix_material_flow_audit_hash', 'material_flow', ['audit_hash'])
    op.create_index('ix_material_flow_period', 'material_flow', ['flow_date', 'direction'])
    op.create_index(
        'ix_material_flow_material_period', 'material_flow', ['material', 'flow_date']
    )

    with op.batch_alter_table('components', schema=None) as batch_op:
        batch_op.add_column(sa.Column('mass_kg', sa.Float(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('components', schema=None) as batch_op:
        batch_op.drop_column('mass_kg')

    op.drop_index('ix_material_flow_material_period', table_name='material_flow')
    op.drop_index('ix_material_flow_period', table_name='material_flow')
    op.drop_index('ix_material_flow_audit_hash', table_name='material_flow')
    op.drop_index('ix_material_flow_flow_date', table_name='material_flow')
    op.drop_index('ix_material_flow_outflow_route', table_name='material_flow')
    op.drop_index('ix_material_flow_direction', table_name='material_flow')
    op.drop_index('ix_material_flow_to_state', table_name='material_flow')
    op.drop_index('ix_material_flow_material', table_name='material_flow')
    op.drop_index('ix_material_flow_component_type', table_name='material_flow')
    op.drop_index('ix_material_flow_component_id', table_name='material_flow')
    op.drop_index('ix_material_flow_component_pk', table_name='material_flow')
    op.drop_table('material_flow')
