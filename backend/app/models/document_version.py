import uuid

from sqlalchemy import JSON, Column, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID

from app.database import Base


class DocumentVersion(Base):
    """Version archivée d'un document. `remplacee_at IS NULL` = version courante."""

    __tablename__ = "document_versions"
    __table_args__ = (UniqueConstraint("doc_id", "version", name="uq_document_versions_doc_version"),)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    doc_id = Column(String, nullable=False, index=True)
    version = Column(Integer, nullable=False)
    filename = Column(String, nullable=False)
    content_hash = Column(String(64), nullable=True)
    stored_path = Column(String, nullable=True)
    nb_chunks = Column(Integer, nullable=False, default=0, server_default="0")
    taille_octets = Column(Integer, nullable=True)
    uploaded_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    # Renseigné quand cette version est née de la restauration d'une version antérieure.
    restauree_depuis = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    remplacee_at = Column(DateTime(timezone=True), nullable=True)
    # stocké, non recalculé — l'archive sortante peut avoir été purgée quand la liste « à relire » est consultée
    changements = Column(JSON, nullable=True)  # {"nb_ajoutes", "nb_retires", "extraits_ajoutes": [≤3]
