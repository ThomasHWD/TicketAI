"""add_reponse_source_id_to_reponses

Revision ID: ea3a267cdf79
Revises: c08be510ad8d
Create Date: 2026-07-16 12:27:31.804297

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'ea3a267cdf79'
down_revision: Union[str, Sequence[str], None] = 'c08be510ad8d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('reponses',
        sa.Column('reponse_source_id', sa.UUID(), nullable=True)
    )
    op.create_foreign_key(
        'reponses_reponse_source_id_fkey',
        'reponses', 'reponses',
        ['reponse_source_id'], ['id']
    )


def downgrade() -> None:
    op.drop_constraint('reponses_reponse_source_id_fkey', 'reponses', type_='foreignkey')
    op.drop_column('reponses', 'reponse_source_id')
