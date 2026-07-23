"""add_objet_to_tickets

Revision ID: b4f2a1c9d3e7
Revises: 3d829af6d66e
Create Date: 2026-07-23 16:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'b4f2a1c9d3e7'
down_revision: Union[str, Sequence[str], None] = '3d829af6d66e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Titre court affiché dans les tableaux/à la place de la question (métadonnée, non utilisé par le RAG).
    op.add_column('tickets', sa.Column('objet', sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column('tickets', 'objet')
