"""add version to reponse_chunks

Revision ID: 8d2f4b6a1e93
Revises: 3c7e1a9d2b40
Create Date: 2026-09-28 14:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "8d2f4b6a1e93"
down_revision: Union[str, Sequence[str], None] = "3c7e1a9d2b40"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("reponse_chunks", sa.Column("version", sa.Integer(), nullable=True))
    # Backfill: the version that was live when the passage was cited. No match → NULL (matched by index as before).
    op.execute(
        """
        UPDATE reponse_chunks rc
        SET version = dv.version
        FROM document_versions dv
        WHERE dv.doc_id = rc.doc_id
          AND dv.created_at <= rc.created_at
          AND (dv.remplacee_at IS NULL OR rc.created_at < dv.remplacee_at)
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("reponse_chunks", "version")
