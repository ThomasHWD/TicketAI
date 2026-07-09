"""add_nb_utilisations_to_tickets

Revision ID: a8b41cb5812a
Revises: e827df9d0869
Create Date: 2026-07-09 10:33:47.492946

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a8b41cb5812a'
down_revision: Union[str, Sequence[str], None] = 'e827df9d0869'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('tickets',
        sa.Column('occurence', sa.Integer(), nullable=False, server_default='0')
    )


def downgrade() -> None:
    op.drop_column('tickets', 'occurence')
