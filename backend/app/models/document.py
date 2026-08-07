import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID

from app.database import Base


class Document(Base):
    """Source de vérité des documents indexés.

    Qdrant reste le magasin des chunks, mais l'identité d'un document (son ``doc_id``,
    sa version courante, son statut) vit ici : un scroll intégral de la collection ne
    permet ni de verrouiller une mise à jour, ni de conserver la trace d'un document
    supprimé.
    """

    __tablename__ = "documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    doc_id = Column(String, nullable=False, unique=True, index=True)
    version = Column(Integer, nullable=False, default=1, server_default="1")
    filename = Column(String, nullable=False)
    domaine = Column(String(50), nullable=False, index=True)
    description = Column(Text, nullable=False, default="", server_default="")
    # NULL sur les documents backfillés : leur payload Qdrant est antérieur au champ.
    content_hash = Column(String(64), nullable=True, index=True)
    stored_path = Column(String, nullable=True)
    nb_chunks = Column(Integer, nullable=False, default=0, server_default="0")
    # ACTIF | EN_MAJ | SUPPRIMÉ — EN_MAJ sert de verrou applicatif contre une mise à
    # jour concurrente et contre un DELETE pendant l'ingestion.
    statut = Column(String(20), nullable=False, default="ACTIF", server_default="ACTIF")
    uploaded_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    update_job_id = Column(String, nullable=True)
    update_started_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    deleted_at = Column(DateTime(timezone=True), nullable=True)
