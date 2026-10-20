"""Saved simulation scenarios and vendor-neutral telemetry.

``simulation_scenarios`` holds simulated what-ifs attached to a real
component. It is a separate table precisely so that no fleet report can
count a simulated part.

``telemetry_readings`` is where readings from any sensor or controller
export land, so the platform has a path to real usage and condition data
that does not depend on a KONE API account.

Revision ID: 0017_field_data
Revises: 0016_material_grade
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0017_field_data'
down_revision: Union[str, None] = '0016_material_grade'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'simulation_scenarios',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('component_id', sa.Integer(), sa.ForeignKey('components.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(length=96), nullable=False),
        sa.Column('load_kg', sa.Float(), nullable=False),
        sa.Column('historical_load_kg', sa.Float(), nullable=True),
        sa.Column('months_simulated', sa.Integer(), nullable=False),
        sa.Column('summary', sa.JSON(), nullable=False),
        sa.Column('created_by', sa.String(length=96), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_simulation_scenarios_component_id', 'simulation_scenarios', ['component_id'])

    op.create_table(
        'telemetry_readings',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('component_id', sa.Integer(), sa.ForeignKey('components.id', ondelete='CASCADE'), nullable=False),
        sa.Column('recorded_at', sa.DateTime(), nullable=False),
        sa.Column('source', sa.String(length=48), nullable=False),
        sa.Column('trips', sa.Integer(), nullable=True),
        sa.Column('run_seconds', sa.Float(), nullable=True),
        sa.Column('load_kg', sa.Float(), nullable=True),
        sa.Column('load_percent', sa.Float(), nullable=True),
        sa.Column('vibration', sa.Float(), nullable=True),
        sa.Column('temperature', sa.Float(), nullable=True),
        sa.Column('received_at', sa.DateTime(), nullable=False),
        sa.Column('received_by', sa.String(length=96), nullable=False),
        sa.UniqueConstraint('component_id', 'recorded_at', 'source', name='uq_telemetry_reading'),
    )
    op.create_index('ix_telemetry_readings_component_id', 'telemetry_readings', ['component_id'])
    op.create_index('ix_telemetry_component_time', 'telemetry_readings', ['component_id', 'recorded_at'])


def downgrade() -> None:
    op.drop_index('ix_telemetry_component_time', table_name='telemetry_readings')
    op.drop_index('ix_telemetry_readings_component_id', table_name='telemetry_readings')
    op.drop_table('telemetry_readings')
    op.drop_index('ix_simulation_scenarios_component_id', table_name='simulation_scenarios')
    op.drop_table('simulation_scenarios')
