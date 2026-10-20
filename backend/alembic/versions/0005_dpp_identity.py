"""Digital Product Passport identity on components.

CPR (EU) 2024/3110 requires a DPP to carry a persistent unique identifier and
to name the economic operator a market-surveillance authority contacts. Both
are nullable: the identifier falls back to one derived from component_id, and
the economic operator to the deployment-wide default, so existing rows stay
valid while a real operator is assigned.

Revision ID: 0005_dpp_identity
Revises: 0004_material_flow
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0005_dpp_identity'
down_revision: Union[str, None] = '0004_material_flow'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('components', schema=None) as batch_op:
        batch_op.add_column(sa.Column('dpp_id', sa.String(length=128), nullable=True))
        batch_op.add_column(sa.Column('economic_operator', sa.String(length=160), nullable=True))
        batch_op.add_column(sa.Column('economic_operator_id', sa.String(length=64), nullable=True))
        batch_op.create_index('ix_components_dpp_id', ['dpp_id'], unique=True)


def downgrade() -> None:
    with op.batch_alter_table('components', schema=None) as batch_op:
        batch_op.drop_index('ix_components_dpp_id')
        batch_op.drop_column('economic_operator_id')
        batch_op.drop_column('economic_operator')
        batch_op.drop_column('dpp_id')
