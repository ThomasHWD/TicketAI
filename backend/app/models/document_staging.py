import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID

from app.database import Base


class DocumentStaging(Base):
    """Fichier téléversé en attente de confirmation. Garantit que la confirmation porte sur le fichier dont l'impact"""

    __tablename__ = "document_staging"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    doc_id = Column(String, nullable=False, index=True)
    # Seul le déposant peut confirmer son propre aperçu.
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    stored_path = Column(String, nullable=False)
    filename = Column(String, nullable=False)
    content_hash = Column(String(64), nullable=True)
    description = Column(Text, nullable=False, default="", server_default="")
    # Mémorisé à l'aperçu pour que la confirmation n'ait à porter que `staging_id`.
    nb_obsoletes = Column(Integer, nullable=False, default=0, server_default="0")
    # Renseigné quand l'aperçu provient de la restauration d'une version archivée.
    restauree_depuis = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=False)
