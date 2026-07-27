"""add prenom nom to users

Revision ID: 99cd36ae01b1
Revises: b4f2a1c9d3e7
Create Date: 2026-07-27 12:22:58.770935

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '99cd36ae01b1'
down_revision: Union[str, Sequence[str], None] = 'b4f2a1c9d3e7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('prenom', sa.String(100), nullable=True))
    op.add_column('users', sa.Column('nom', sa.String(100), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'nom')
    op.drop_column('users', 'prenom')
