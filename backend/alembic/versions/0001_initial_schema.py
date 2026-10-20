"""Initial KONE ELEVATE schema.

Creates the seven core tables: components, service_events, predictions,
recovery_items, service_demands, recovery_matches and audit_logs, together
with the indexes that back the components table filters and the audit chain.

Revision ID: 0001_initial
Revises:
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0001_initial'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('audit_logs',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('entity_type', sa.String(length=48), nullable=False),
    sa.Column('entity_id', sa.String(length=64), nullable=False),
    sa.Column('action', sa.String(length=32), nullable=False),
    sa.Column('data_snapshot', sa.JSON(), nullable=True),
    sa.Column('previous_hash', sa.String(length=64), nullable=False),
    sa.Column('current_hash', sa.String(length=64), nullable=False),
    sa.Column('timestamp', sa.DateTime(), nullable=False),
    sa.Column('actor', sa.String(length=96), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('audit_logs', schema=None) as batch_op:
        batch_op.create_index('ix_audit_entity', ['entity_type', 'entity_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_audit_logs_action'), ['action'], unique=False)
        batch_op.create_index(batch_op.f('ix_audit_logs_current_hash'), ['current_hash'], unique=True)
        batch_op.create_index(batch_op.f('ix_audit_logs_entity_id'), ['entity_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_audit_logs_entity_type'), ['entity_type'], unique=False)
        batch_op.create_index(batch_op.f('ix_audit_logs_timestamp'), ['timestamp'], unique=False)

    op.create_table('components',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('component_id', sa.String(length=48), nullable=False),
    sa.Column('serial_number', sa.String(length=64), nullable=False),
    sa.Column('component_type', sa.String(length=48), nullable=False),
    sa.Column('material', sa.String(length=32), nullable=False),
    sa.Column('manufacturer', sa.String(length=96), nullable=True),
    sa.Column('origin', sa.String(length=96), nullable=True),
    sa.Column('installation_date', sa.Date(), nullable=True),
    sa.Column('operating_hours', sa.Float(), nullable=False),
    sa.Column('load_cycles', sa.Integer(), nullable=False),
    sa.Column('average_load', sa.Float(), nullable=False),
    sa.Column('vibration', sa.Float(), nullable=False),
    sa.Column('temperature', sa.Float(), nullable=False),
    sa.Column('service_count', sa.Integer(), nullable=False),
    sa.Column('repair_count', sa.Integer(), nullable=False),
    sa.Column('failure_history', sa.Integer(), nullable=False),
    sa.Column('inspection_score', sa.Float(), nullable=False),
    sa.Column('last_service_date', sa.Date(), nullable=True),
    sa.Column('health_score', sa.Float(), nullable=True),
    sa.Column('current_status', sa.String(length=32), nullable=False),
    sa.Column('location', sa.String(length=96), nullable=True),
    sa.Column('qr_token', sa.String(length=48), nullable=False),
    sa.Column('notes', sa.String(length=512), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('components', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_components_component_id'), ['component_id'], unique=True)
        batch_op.create_index(batch_op.f('ix_components_component_type'), ['component_type'], unique=False)
        batch_op.create_index(batch_op.f('ix_components_current_status'), ['current_status'], unique=False)
        batch_op.create_index(batch_op.f('ix_components_health_score'), ['health_score'], unique=False)
        batch_op.create_index(batch_op.f('ix_components_installation_date'), ['installation_date'], unique=False)
        batch_op.create_index(batch_op.f('ix_components_location'), ['location'], unique=False)
        batch_op.create_index(batch_op.f('ix_components_material'), ['material'], unique=False)
        batch_op.create_index(batch_op.f('ix_components_origin'), ['origin'], unique=False)
        batch_op.create_index(batch_op.f('ix_components_qr_token'), ['qr_token'], unique=True)
        batch_op.create_index(batch_op.f('ix_components_serial_number'), ['serial_number'], unique=True)
        batch_op.create_index('ix_components_status_health', ['current_status', 'health_score'], unique=False)
        batch_op.create_index('ix_components_type_status', ['component_type', 'current_status'], unique=False)

    op.create_table('service_demands',
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
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('service_demands', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_service_demands_location'), ['location'], unique=False)
        batch_op.create_index(batch_op.f('ix_service_demands_priority'), ['priority'], unique=False)
        batch_op.create_index(batch_op.f('ix_service_demands_reference'), ['reference'], unique=True)
        batch_op.create_index(batch_op.f('ix_service_demands_required_component_type'), ['required_component_type'], unique=False)
        batch_op.create_index(batch_op.f('ix_service_demands_required_material'), ['required_material'], unique=False)
        batch_op.create_index(batch_op.f('ix_service_demands_status'), ['status'], unique=False)
        batch_op.create_index('ix_service_demands_type_status', ['required_component_type', 'status'], unique=False)

    op.create_table('predictions',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('component_id', sa.Integer(), nullable=False),
    sa.Column('health_score', sa.Float(), nullable=False),
    sa.Column('recommendation', sa.String(length=16), nullable=False),
    sa.Column('confidence', sa.Float(), nullable=False),
    sa.Column('model_version', sa.String(length=48), nullable=False),
    sa.Column('key_factors', sa.JSON(), nullable=True),
    sa.Column('input_snapshot', sa.JSON(), nullable=True),
    sa.Column('probabilities', sa.JSON(), nullable=True),
    sa.Column('safety_flag', sa.Boolean(), nullable=False),
    sa.Column('safety_message', sa.String(length=128), nullable=True),
    sa.Column('predicted_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['component_id'], ['components.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('predictions', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_predictions_component_id'), ['component_id'], unique=False)
        batch_op.create_index('ix_predictions_component_time', ['component_id', 'predicted_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_predictions_predicted_at'), ['predicted_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_predictions_recommendation'), ['recommendation'], unique=False)
        batch_op.create_index('ix_predictions_recommendation_time', ['recommendation', 'predicted_at'], unique=False)

    op.create_table('recovery_items',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('component_id', sa.Integer(), nullable=False),
    sa.Column('condition', sa.String(length=24), nullable=False),
    sa.Column('availability_status', sa.String(length=24), nullable=False),
    sa.Column('estimated_value', sa.Float(), nullable=False),
    sa.Column('estimated_co2_saving', sa.Float(), nullable=False),
    sa.Column('location', sa.String(length=96), nullable=True),
    sa.Column('available_from', sa.Date(), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['component_id'], ['components.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('recovery_items', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_recovery_items_availability_status'), ['availability_status'], unique=False)
        batch_op.create_index(batch_op.f('ix_recovery_items_component_id'), ['component_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_recovery_items_condition'), ['condition'], unique=False)
        batch_op.create_index(batch_op.f('ix_recovery_items_location'), ['location'], unique=False)
        batch_op.create_index('ix_recovery_items_status_condition', ['availability_status', 'condition'], unique=False)

    op.create_table('service_events',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('component_id', sa.Integer(), nullable=False),
    sa.Column('event_type', sa.String(length=32), nullable=False),
    sa.Column('event_date', sa.Date(), nullable=False),
    sa.Column('technician', sa.String(length=96), nullable=True),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('operating_hours', sa.Float(), nullable=True),
    sa.Column('vibration', sa.Float(), nullable=True),
    sa.Column('temperature', sa.Float(), nullable=True),
    sa.Column('inspection_score', sa.Float(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['component_id'], ['components.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('service_events', schema=None) as batch_op:
        batch_op.create_index('ix_service_events_component_date', ['component_id', 'event_date'], unique=False)
        batch_op.create_index(batch_op.f('ix_service_events_component_id'), ['component_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_service_events_event_date'), ['event_date'], unique=False)
        batch_op.create_index(batch_op.f('ix_service_events_event_type'), ['event_type'], unique=False)

    op.create_table('recovery_matches',
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
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('recovery_matches', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_recovery_matches_match_score'), ['match_score'], unique=False)
        batch_op.create_index('ix_recovery_matches_pair', ['recovery_item_id', 'service_demand_id'], unique=True)
        batch_op.create_index(batch_op.f('ix_recovery_matches_recovery_item_id'), ['recovery_item_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_recovery_matches_service_demand_id'), ['service_demand_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_recovery_matches_status'), ['status'], unique=False)



def downgrade() -> None:
    with op.batch_alter_table('recovery_matches', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_recovery_matches_status'))
        batch_op.drop_index(batch_op.f('ix_recovery_matches_service_demand_id'))
        batch_op.drop_index(batch_op.f('ix_recovery_matches_recovery_item_id'))
        batch_op.drop_index('ix_recovery_matches_pair')
        batch_op.drop_index(batch_op.f('ix_recovery_matches_match_score'))

    op.drop_table('recovery_matches')
    with op.batch_alter_table('service_events', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_service_events_event_type'))
        batch_op.drop_index(batch_op.f('ix_service_events_event_date'))
        batch_op.drop_index(batch_op.f('ix_service_events_component_id'))
        batch_op.drop_index('ix_service_events_component_date')

    op.drop_table('service_events')
    with op.batch_alter_table('recovery_items', schema=None) as batch_op:
        batch_op.drop_index('ix_recovery_items_status_condition')
        batch_op.drop_index(batch_op.f('ix_recovery_items_location'))
        batch_op.drop_index(batch_op.f('ix_recovery_items_condition'))
        batch_op.drop_index(batch_op.f('ix_recovery_items_component_id'))
        batch_op.drop_index(batch_op.f('ix_recovery_items_availability_status'))

    op.drop_table('recovery_items')
    with op.batch_alter_table('predictions', schema=None) as batch_op:
        batch_op.drop_index('ix_predictions_recommendation_time')
        batch_op.drop_index(batch_op.f('ix_predictions_recommendation'))
        batch_op.drop_index(batch_op.f('ix_predictions_predicted_at'))
        batch_op.drop_index('ix_predictions_component_time')
        batch_op.drop_index(batch_op.f('ix_predictions_component_id'))

    op.drop_table('predictions')
    with op.batch_alter_table('service_demands', schema=None) as batch_op:
        batch_op.drop_index('ix_service_demands_type_status')
        batch_op.drop_index(batch_op.f('ix_service_demands_status'))
        batch_op.drop_index(batch_op.f('ix_service_demands_required_material'))
        batch_op.drop_index(batch_op.f('ix_service_demands_required_component_type'))
        batch_op.drop_index(batch_op.f('ix_service_demands_reference'))
        batch_op.drop_index(batch_op.f('ix_service_demands_priority'))
        batch_op.drop_index(batch_op.f('ix_service_demands_location'))

    op.drop_table('service_demands')
    with op.batch_alter_table('components', schema=None) as batch_op:
        batch_op.drop_index('ix_components_type_status')
        batch_op.drop_index('ix_components_status_health')
        batch_op.drop_index(batch_op.f('ix_components_serial_number'))
        batch_op.drop_index(batch_op.f('ix_components_qr_token'))
        batch_op.drop_index(batch_op.f('ix_components_origin'))
        batch_op.drop_index(batch_op.f('ix_components_material'))
        batch_op.drop_index(batch_op.f('ix_components_location'))
        batch_op.drop_index(batch_op.f('ix_components_installation_date'))
        batch_op.drop_index(batch_op.f('ix_components_health_score'))
        batch_op.drop_index(batch_op.f('ix_components_current_status'))
        batch_op.drop_index(batch_op.f('ix_components_component_type'))
        batch_op.drop_index(batch_op.f('ix_components_component_id'))

    op.drop_table('components')
    with op.batch_alter_table('audit_logs', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_audit_logs_timestamp'))
        batch_op.drop_index(batch_op.f('ix_audit_logs_entity_type'))
        batch_op.drop_index(batch_op.f('ix_audit_logs_entity_id'))
        batch_op.drop_index(batch_op.f('ix_audit_logs_current_hash'))
        batch_op.drop_index(batch_op.f('ix_audit_logs_action'))
        batch_op.drop_index('ix_audit_entity')

    op.drop_table('audit_logs')
