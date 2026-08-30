"""add garde_verdict and garde_justification to reponses

Trace du verdict rendu par le garde anti « cache over-hit »
(``services/garde_cache.py``) sur les réponses servies en branche CANONIQUE.

Ces réponses partent chez l'employé avec ``statut="VALIDÉE"`` alors qu'aucun
humain ne les a relues. Jusqu'ici rien ne les distinguait en base d'une
validation manuelle — ``validator_id`` et ``validated_at`` sont NULL dans les
deux cas — et le taux d'erreur des juges en production était donc immesurable.

NULL partout ailleurs : branche RAG, branche SUGGESTION, validation humaine.

Revision ID: a1c7e93f2b58
Revises: 5d82e8c2c38e
Create Date: 2026-08-30 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1c7e93f2b58"
down_revision: Union[str, Sequence[str], None] = "5d82e8c2c38e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("reponses", sa.Column("garde_verdict", sa.String(length=30), nullable=True))
    op.add_column("reponses", sa.Column("garde_justification", sa.Text(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("reponses", "garde_justification")
    op.drop_column("reponses", "garde_verdict")
