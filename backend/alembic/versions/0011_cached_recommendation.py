"""Cache the latest recommendation/confidence on components (P4 scale fix).

Adds ``components.latest_recommendation`` / ``latest_confidence``, refreshed
on every assessment the same way ``health_score`` already is (see
``app.services.prediction_service.assess_component``). Backfilled from
existing prediction history so a deployment upgrading mid-flight does not
show a blank dashboard the moment this lands.

This exists because measuring the P4 SQL-aggregation rewrite against a real
200k-component / 600k-prediction load test (``scripts/load_test.py``)
showed the join-and-``MAX(id)``-per-component subquery
(``app.api.dashboard._latest_prediction_subquery``) still scanned the
entire, forever-growing ``predictions`` table on every dashboard request -
p95 1.75s on ``/dashboard/summary``. Reading a cached column instead of
recomputing "what is the current state" from full history on every request
is the same idea ``health_score`` already applied; this closes the one
place that idea was not yet applied.

Revision ID: 0011_cached_recommendation
Revises: 0010_partition_service_events
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0011_cached_recommendation'
down_revision: Union[str, None] = '0010_partition_service_events'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('components', schema=None) as batch_op:
        batch_op.add_column(sa.Column('latest_recommendation', sa.String(length=24), nullable=True))
        batch_op.add_column(sa.Column('latest_confidence', sa.Float(), nullable=True))
        batch_op.create_index('ix_components_latest_recommendation', ['latest_recommendation'])

    # Backfill from the most recent prediction per component (predictions
    # are append-only, so "most recent" is "highest id" - see
    # app.api.dashboard's own module docstring for the same reasoning).
    op.execute(
        """
        UPDATE components
        SET latest_recommendation = latest.recommendation,
            latest_confidence = latest.confidence
        FROM (
            SELECT DISTINCT ON (component_id) component_id, recommendation, confidence
            FROM predictions
            ORDER BY component_id, id DESC
        ) AS latest
        WHERE components.id = latest.component_id
        """
        if op.get_bind().dialect.name == "postgresql"
        else """
        UPDATE components
        SET latest_recommendation = (
            SELECT p.recommendation FROM predictions p
            WHERE p.component_id = components.id ORDER BY p.id DESC LIMIT 1
        ),
        latest_confidence = (
            SELECT p.confidence FROM predictions p
            WHERE p.component_id = components.id ORDER BY p.id DESC LIMIT 1
        )
        WHERE EXISTS (SELECT 1 FROM predictions p WHERE p.component_id = components.id)
        """
    )


def downgrade() -> None:
    with op.batch_alter_table('components', schema=None) as batch_op:
        batch_op.drop_index('ix_components_latest_recommendation')
        batch_op.drop_column('latest_confidence')
        batch_op.drop_column('latest_recommendation')
