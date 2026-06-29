import uuid

from sqlalchemy import Column, DateTime, Float, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.database import Base


class Reponse(Base):
    __tablename__ = "reponses"

    id               = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ticket_id        = Column(UUID(as_uuid=True), ForeignKey("tickets.id"), nullable=False)
    contenu          = Column(Text, nullable=False)
    statut           = Column(String(20), nullable=False, default="EN_ATTENTE")
                       # EN_ATTENTE / VALIDÉE / REJETÉE / CORRIGÉE
    source           = Column(String(20), nullable=False)
                       # LLM / CANONIQUE
    contenu_corrige  = Column(Text, nullable=True)
    score_similarite = Column(Float, nullable=True)
    validator_id     = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    validated_at     = Column(DateTime(timezone=True), nullable=True)
    created_at       = Column(DateTime(timezone=True), server_default=func.now())

    ticket           = relationship("Ticket", back_populates="reponses")
    validator        = relationship("User", foreign_keys=[validator_id])
