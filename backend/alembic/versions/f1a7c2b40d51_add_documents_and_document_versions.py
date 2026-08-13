"""add documents and document_versions

Revision ID: f1a7c2b40d51
Revises: cab68e932c9f
Create Date: 2026-08-07 10:12:03.441027

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f1a7c2b40d51"
down_revision: Union[str, Sequence[str], None] = "cab68e932c9f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "documents",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("doc_id", sa.String(), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("filename", sa.String(), nullable=False),
        sa.Column("domaine", sa.String(length=50), nullable=False),
        sa.Column("description", sa.Text(), server_default="", nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=True),
        sa.Column("stored_path", sa.String(), nullable=True),
        sa.Column("nb_chunks", sa.Integer(), server_default="0", nullable=False),
        sa.Column("statut", sa.String(length=20), server_default="ACTIF", nullable=False),
        sa.Column("uploaded_by", sa.UUID(), nullable=True),
        sa.Column("update_job_id", sa.String(), nullable=True),
        sa.Column("update_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["uploaded_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    # L'unicité de doc_id est portée par l'index, pas par une contrainte séparée
    # (`Column(unique=True, index=True)` ne génère qu'un index unique).
    op.create_index(op.f("ix_documents_doc_id"), "documents", ["doc_id"], unique=True)
    op.create_index(op.f("ix_documents_domaine"), "documents", ["domaine"])
    op.create_index(op.f("ix_documents_content_hash"), "documents", ["content_hash"])

    op.create_table(
        "document_versions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("doc_id", sa.String(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("filename", sa.String(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=True),
        sa.Column("stored_path", sa.String(), nullable=True),
        sa.Column("nb_chunks", sa.Integer(), server_default="0", nullable=False),
        sa.Column("taille_octets", sa.Integer(), nullable=True),
        sa.Column("uploaded_by", sa.UUID(), nullable=True),
        sa.Column("restauree_depuis", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("remplacee_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["uploaded_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("doc_id", "version", name="uq_document_versions_doc_version"),
    )
    op.create_index(op.f("ix_document_versions_doc_id"), "document_versions", ["doc_id"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_document_versions_doc_id"), table_name="document_versions")
    op.drop_table("document_versions")
    op.drop_index(op.f("ix_documents_content_hash"), table_name="documents")
    op.drop_index(op.f("ix_documents_domaine"), table_name="documents")
    op.drop_index(op.f("ix_documents_doc_id"), table_name="documents")
    op.drop_table("documents")
