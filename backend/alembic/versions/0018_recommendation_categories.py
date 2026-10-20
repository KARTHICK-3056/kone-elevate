"""Rename stored values to the four recommendation categories.

The recommendation vocabulary changed from Reuse / Refurbish / Recycle /
Dispose to Continue Using – No Changes Required / Component Recovery /
Material Recovery / Dispose, with matching lifecycle states, recovery
conditions, workshop outcomes, a service-event type and a role. This
rewrites every stored copy of the old codes so reports, filters and the
lifecycle state machine see one vocabulary.

``audit_logs`` is deliberately NOT touched. It is hash-chained: rewriting a
payload would break verification, and the chain is meant to say what was
recorded at the time. Old codes read from it are mapped on read by
``app.utils.enums.canonical_recommendation``. The ``material_flow`` rows keep
their ``audit_hash``; only the state vocabulary on the row is renamed.

``rename_values(connection)`` is also used by
``scripts/migrate_dev_db.py`` for the local SQLite database, which is
created by ``create_all`` rather than by Alembic.

Revision ID: 0018_recommendation_categories
Revises: 0017_field_data
"""
import json
from typing import Dict, Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0018_recommendation_categories'
down_revision: Union[str, None] = '0017_field_data'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


RECOMMENDATIONS: Dict[str, str] = {
    'REUSE': 'CONTINUE_USING',
    'REFURBISH': 'COMPONENT_RECOVERY',
    'RECYCLE': 'MATERIAL_RECOVERY',
}
LIFECYCLE: Dict[str, str] = {
    'REFURBISHMENT': 'PART_RECOVERY',
    'RECYCLED': 'MATERIAL_RECOVERED',
}
ITEM_CONDITIONS: Dict[str, str] = {
    'REUSABLE': 'PARTS_TESTED',
    'REFURBISHABLE': 'PARTS_AWAITING_TEST',
    'RECYCLABLE': 'MATERIAL_ONLY',
}
#: A demand may only ask for recovered parts; a "recyclable" minimum is the
#: least demanding requirement left.
DEMAND_CONDITIONS: Dict[str, str] = {
    'REUSABLE': 'PARTS_TESTED',
    'REFURBISHABLE': 'PARTS_AWAITING_TEST',
    'RECYCLABLE': 'PARTS_AWAITING_TEST',
}
WORKSHOP_OUTCOMES: Dict[str, str] = {
    'REUSED_AS_IS': 'CONTINUED_IN_SERVICE',
    'REFURBISHED_AND_REDEPLOYED': 'PARTS_RECOVERED',
    'RECYCLED': 'MATERIAL_RECOVERED',
}
EVENT_TYPES: Dict[str, str] = {'REINSTALLATION': 'PARTS_FITTED'}
ROLES: Dict[str, str] = {'refurbishment_planner': 'recovery_planner'}

#: (table, column, mapping)
COLUMNS = [
    ('predictions', 'recommendation', RECOMMENDATIONS),
    ('predictions', 'underlying_recommendation', RECOMMENDATIONS),
    ('components', 'latest_recommendation', RECOMMENDATIONS),
    ('components', 'current_status', LIFECYCLE),
    ('material_flow', 'from_state', LIFECYCLE),
    ('material_flow', 'to_state', LIFECYCLE),
    ('recovery_items', 'condition', ITEM_CONDITIONS),
    ('recovery_items', 'workshop_outcome', WORKSHOP_OUTCOMES),
    ('service_demands', 'minimum_condition', DEMAND_CONDITIONS),
    ('service_events', 'event_type', EVENT_TYPES),
    ('users', 'role', ROLES),
]


def _rename_columns(connection, columns, inverse: bool = False) -> None:
    existing = set(sa.inspect(connection).get_table_names())
    for table, column, mapping in columns:
        if table not in existing:
            continue
        pairs = {new: old for old, new in mapping.items()} if inverse else mapping
        for old, new in pairs.items():
            connection.execute(
                sa.text(f'UPDATE {table} SET {column} = :new WHERE {column} = :old'),
                {'new': new, 'old': old},
            )


def _rename_probability_keys(connection, mapping: Dict[str, str]) -> None:
    """Rename the class keys inside each stored probability distribution."""
    rows = connection.execute(
        sa.text('SELECT id, probabilities FROM predictions WHERE probabilities IS NOT NULL')
    ).fetchall()
    for row_id, raw in rows:
        value = json.loads(raw) if isinstance(raw, str) else raw
        if not isinstance(value, dict) or not any(key in mapping for key in value):
            continue
        renamed = {mapping.get(key, key): prob for key, prob in value.items()}
        target = 'CAST(:value AS JSON)' if connection.dialect.name == 'postgresql' else ':value'
        connection.execute(
            sa.text(f'UPDATE predictions SET probabilities = {target} WHERE id = :id'),
            {'value': json.dumps(renamed), 'id': row_id},
        )


def rename_values(connection) -> None:
    """Rename every stored old code to its new code (never audit_logs)."""
    _rename_columns(connection, COLUMNS)
    if 'predictions' in set(sa.inspect(connection).get_table_names()):
        _rename_probability_keys(connection, RECOMMENDATIONS)


def upgrade() -> None:
    rename_values(op.get_bind())


def downgrade() -> None:
    # Best-effort inverse. Two demand minimums collapse into one on upgrade,
    # so a downgraded RECYCLABLE minimum comes back as REFURBISHABLE.
    connection = op.get_bind()
    _rename_columns(
        connection,
        [(t, c, m if m is not DEMAND_CONDITIONS else ITEM_CONDITIONS) for t, c, m in COLUMNS],
        inverse=True,
    )
    _rename_probability_keys(connection, {new: old for old, new in RECOMMENDATIONS.items()})
