"""add_tag_to_reponses

Revision ID: 0c8261578c28
Revises: b1e9f3a2d8c0
Create Date: 2026-09-09 15:01:24.137936

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '0c8261578c28'
down_revision: Union[str, Sequence[str], None] = 'b1e9f3a2d8c0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('reponses', sa.Column('tag', sa.String(length=100), nullable=True))


def downgrade() -> None:
    op.drop_column('reponses', 'tag')
