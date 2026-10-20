"""Record the specific material grade of a component.

Adds ``components.material_grade``. Raised at the first mentor review: a
passport that says only "Steel" or "Cast Iron" cannot explain why two parts
of the same type last differently. The grade (ductile vs grey iron sheave,
sintered vs polymer brake lining, Class F vs Class H motor) is what the
usage-adjusted life model in ``app.ml.life_model`` scales design life by.

Nullable, no default: an unrecorded grade is assumed from ``material`` at
read time and the passport says it was assumed, so existing rows need no
backfill.

Revision ID: 0016_material_grade
Revises: 0015_prediction_life
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0016_material_grade'
down_revision: Union[str, None] = '0015_prediction_life'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('components', schema=None) as batch_op:
        batch_op.add_column(sa.Column('material_grade', sa.String(length=48), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('components', schema=None) as batch_op:
        batch_op.drop_column('material_grade')
