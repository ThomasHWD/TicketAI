"""add_thread_fields_to_ticket

Revision ID: 3d829af6d66e
Revises: 7c1e4b9af2d0
Create Date: 2026-07-23 10:21:45.138784

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '3d829af6d66e'
down_revision: Union[str, Sequence[str], None] = '7c1e4b9af2d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Clôture du ticket par l'utilisateur (NULL = ouvert).
    op.add_column('tickets', sa.Column('closed_at', sa.DateTime(timezone=True), nullable=True))
    # Texte de la précision qui a déclenché cette réponse (NULL = réponse à la question initiale).
    op.add_column('reponses', sa.Column('question_suivi', sa.Text, nullable=True))


def downgrade() -> None:
    op.drop_column('reponses', 'question_suivi')
    op.drop_column('tickets', 'closed_at')
