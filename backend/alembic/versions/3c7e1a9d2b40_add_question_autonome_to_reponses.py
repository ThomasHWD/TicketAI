"""add question_autonome to reponses

Revision ID: 3c7e1a9d2b40
Revises: 0fd9990ef06f
Create Date: 2026-09-28 12:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "3c7e1a9d2b40"
down_revision: Union[str, Sequence[str], None] = "0fd9990ef06f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("reponses", sa.Column("question_autonome", sa.Text(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("reponses", "question_autonome")
