"""add analyse_justification and analyse_extraits to reponses

Trace du verdict rendu par la ré-vérification (``workers/reverification.py``)
quand une nouvelle version de document est publiée. Sans elle, une réponse
canonique retirée du service disparaîtrait sans que personne puisse savoir ce
que la nouvelle version disait de contraire.

Les deux colonnes servent indifféremment les drapeaux ``obsolete`` et
``a_relire`` : le verdict qui aggrave et celui qui hésite ont tous deux besoin
d'être justifiés.

Revision ID: c3f5a91e7b204
Revises: e8dfce3550c0
Create Date: 2026-08-12 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c3f5a91e7b204"
down_revision: Union[str, Sequence[str], None] = "e8dfce3550c0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("reponses", sa.Column("analyse_justification", sa.Text(), nullable=True))
    op.add_column("reponses", sa.Column("analyse_extraits", sa.JSON(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("reponses", "analyse_extraits")
    op.drop_column("reponses", "analyse_justification")
