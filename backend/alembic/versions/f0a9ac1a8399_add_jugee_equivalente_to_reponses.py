"""add jugee_equivalente to reponses

Revision ID: f0a9ac1a8399
Revises: 8d2f4b6a1e93
Create Date: 2026-09-29 12:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f0a9ac1a8399"
down_revision: Union[str, Sequence[str], None] = "8d2f4b6a1e93"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "reponses",
        sa.Column("jugee_equivalente", sa.Boolean(), nullable=False, server_default="false"),
    )
    # Backfill only what is provable: an initial-turn copy whose OUI was given on the ticket's own question. A
    # follow-up's verdict was given on a thread, not recoverable as a pair — left false (no propagation, safe side).
    op.execute(
        """
        UPDATE reponses r
        SET jugee_equivalente = true
        FROM tickets t
        WHERE t.id = r.ticket_id
          AND r.reponse_source_id IS NOT NULL
          AND r.question_suivi IS NULL
          AND EXISTS (
            SELECT 1 FROM garde_decisions g
            WHERE g.reponse_id = r.reponse_source_id
              AND g.verdict IS true
              AND g.question_posee = t.question
              AND (g.job_id = t.job_id OR g.ticket_id = t.id)
          )
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("reponses", "jugee_equivalente")
