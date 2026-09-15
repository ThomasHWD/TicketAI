"""add reroute_source_domaine to tickets

Revision ID: 0fd9990ef06f
Revises: 2ccf61ea761e
Create Date: 2026-09-15 10:27:11.515583

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0fd9990ef06f'
down_revision: Union[str, Sequence[str], None] = '2ccf61ea761e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('tickets', sa.Column('reroute_source_domaine', sa.String(length=50), nullable=True))


def downgrade() -> None:
    op.drop_column('tickets', 'reroute_source_domaine')
