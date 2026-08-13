import uuid

from sqlalchemy import JSON, Column, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID

from app.database import Base


class DocumentVersion(Base):
    """Une version archivée d'un document — y compris la version courante.

    ``remplacee_at IS NULL`` identifie la version courante. Le fichier de chaque
    version vit sous ``{documents_storage_path}/{doc_id}/v{version}/{filename}`` ;
    les documents antérieurs au versioning gardent leur fichier à la racine du
    dossier ``{doc_id}`` et ``stored_path`` fait foi.
    """

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
    # Ce que cette version a changé par rapport à la précédente :
    # {"nb_ajoutes", "nb_retires", "extraits_ajoutes": [≤3], "extraits_retires": [≤3]}.
    # Stocké et non recalculé — la liste « à relire » se consulte des jours plus
    # tard, quand l'archive sortante peut avoir été purgée. Sans ces extraits,
    # « cette réponse est liée à Charte_RH v3 » ne permet de juger de rien.
    changements = Column(JSON, nullable=True)
