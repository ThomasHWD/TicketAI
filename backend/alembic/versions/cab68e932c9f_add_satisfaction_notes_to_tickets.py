"""add satisfaction notes to tickets

Revision ID: cab68e932c9f
Revises: fdf0d90ec71c
Create Date: 2026-08-06 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'cab68e932c9f'
down_revision: Union[str, Sequence[str], None] = 'd766907369e7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('tickets', sa.Column('note_qualite', sa.Integer(), nullable=True))
    op.add_column('tickets', sa.Column('note_delai', sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column('tickets', 'note_delai')
    op.drop_column('tickets', 'note_qualite')
