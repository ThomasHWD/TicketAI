"""add_lock_fields_to_tickets

Revision ID: 7c1e4b9af2d0
Revises: 92ede98d9079
Create Date: 2026-07-21 09:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '7c1e4b9af2d0'
down_revision: Union[str, Sequence[str], None] = '92ede98d9079'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('tickets', sa.Column('locked_by', sa.UUID(), nullable=True))
    op.add_column('tickets', sa.Column('locked_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('tickets', sa.Column('lock_expires_at', sa.DateTime(timezone=True), nullable=True))
    op.create_foreign_key(
        'tickets_locked_by_fkey',
        'tickets', 'users',
        ['locked_by'], ['id'],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('tickets_locked_by_fkey', 'tickets', type_='foreignkey')
    op.drop_column('tickets', 'lock_expires_at')
    op.drop_column('tickets', 'locked_at')
    op.drop_column('tickets', 'locked_by')
