import uuid
from sqlalchemy import Column, String, Text, Float, Boolean, DateTime, Integer, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.database import Base

class Ticket(Base):
    __tablename__ = "tickets"

    id               = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    question         = Column(Text, nullable=False)
    domaine          = Column(String(20), nullable=False)  # IT / RH / JURIDIQUE
    user_id          = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    job_id           = Column(UUID(as_uuid=True), unique=True, nullable=False, default=uuid.uuid4)
    statut_job       = Column(String(20), nullable=False, default="EN_ATTENTE")
                       # EN_ATTENTE / EN_COURS / TERMINÉ / ÉCHOUÉ
    statut_ticket    = Column(String(20), nullable=False, default="NOUVEAU")
                       # NOUVEAU / RÉPONDU / VALIDÉ / REJETÉ
    score_similarite = Column(Float, nullable=True)
    canonique        = Column(Boolean, nullable=False, default=False)
    nb_retries       = Column(Integer, nullable=False, default=0)
    erreur           = Column(Text, nullable=True)
    created_at       = Column(DateTime(timezone=True), server_default=func.now())
    processed_at     = Column(DateTime(timezone=True), nullable=True)

    reponses         = relationship("Reponse", back_populates="ticket")
    user             = relationship("User")