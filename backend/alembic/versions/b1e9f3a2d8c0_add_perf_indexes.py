"""add performance indexes on frequently-filtered columns

Revision ID: b1e9f3a2d8c0
Revises: 946fc7c7c75c
Create Date: 2026-09-08 10:00:00.000000

"""

from typing import Sequence, Union

from alembic import op

revision: str = "b1e9f3a2d8c0"
down_revision: Union[str, Sequence[str], None] = "946fc7c7c75c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index("ix_tickets_user_id", "tickets", ["user_id"])
    op.create_index("ix_tickets_statut_ticket", "tickets", ["statut_ticket"])
    op.create_index("ix_tickets_statut_job", "tickets", ["statut_job"])
    op.create_index("ix_tickets_domaine", "tickets", ["domaine"])
    op.create_index("ix_tickets_created_at", "tickets", ["created_at"])
    op.create_index("ix_tickets_assigned_to", "tickets", ["assigned_to"])
    op.create_index("ix_tickets_closed_at", "tickets", ["closed_at"])

    op.create_index("ix_reponses_ticket_id", "reponses", ["ticket_id"])
    op.create_index("ix_reponses_statut", "reponses", ["statut"])
    op.create_index("ix_reponses_canonique", "reponses", ["canonique"])
    op.create_index("ix_reponses_reponse_source_id", "reponses", ["reponse_source_id"])
    op.create_index("ix_reponses_validator_id", "reponses", ["validator_id"])


def downgrade() -> None:
    op.drop_index("ix_reponses_validator_id", table_name="reponses")
    op.drop_index("ix_reponses_reponse_source_id", table_name="reponses")
    op.drop_index("ix_reponses_canonique", table_name="reponses")
    op.drop_index("ix_reponses_statut", table_name="reponses")
    op.drop_index("ix_reponses_ticket_id", table_name="reponses")

    op.drop_index("ix_tickets_closed_at", table_name="tickets")
    op.drop_index("ix_tickets_assigned_to", table_name="tickets")
    op.drop_index("ix_tickets_created_at", table_name="tickets")
    op.drop_index("ix_tickets_domaine", table_name="tickets")
    op.drop_index("ix_tickets_statut_job", table_name="tickets")
    op.drop_index("ix_tickets_statut_ticket", table_name="tickets")
    op.drop_index("ix_tickets_user_id", table_name="tickets")
