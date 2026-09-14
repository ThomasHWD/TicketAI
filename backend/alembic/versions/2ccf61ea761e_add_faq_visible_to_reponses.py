"""add_faq_visible_to_reponses

Revision ID: 2ccf61ea761e
Revises: a7f4c2e91b30
Create Date: 2026-09-14 10:53:25.373409

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '2ccf61ea761e'
down_revision: Union[str, Sequence[str], None] = 'a7f4c2e91b30'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('reponses', sa.Column('faq_visible', sa.Boolean(), server_default='false', nullable=False))


def downgrade() -> None:
    op.drop_column('reponses', 'faq_visible')
