"""Ajoute score_lexical à garde_decisions.

Avec la recherche lexicale, la porte se franchit par le cosinus **ou** par le
score BM25 ramené au terme. `score_cosinus` est conservé tel quel — c'est ce qui permet de
comparer une décision d'aujourd'hui à celles d'avant BM25. Nullable, donc : les
lignes antérieures n'ont pas de score hybride, et n'ont pas à en inventer un.

Revision ID: a7f4c2e91b30
Revises: 0c8261578c28
"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "a7f4c2e91b30"
down_revision: Union[str, Sequence[str], None] = "0c8261578c28"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("garde_decisions", sa.Column("score_lexical", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("garde_decisions", "score_lexical")
