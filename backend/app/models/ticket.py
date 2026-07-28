import uuid

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.database import Base


class Ticket(Base):
    __tablename__ = "tickets"

    id               = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    question         = Column(Text, nullable=False)
    objet            = Column(String(255), nullable=True)  # Titre court d'affichage (hors pipeline RAG)
    domaine          = Column(String(50), nullable=False)  # valeur libre, définie par les groupes admin
    user_id          = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    job_id           = Column(UUID(as_uuid=True), unique=True, nullable=False, default=uuid.uuid4)
    statut_job       = Column(String(20), nullable=False, default="EN_ATTENTE")
                       # EN_ATTENTE / EN_COURS / TERMINÉ / ÉCHOUÉ
    statut_ticket    = Column(String(20), nullable=False, default="NOUVEAU")
                       # NOUVEAU / RÉPONDU / VALIDÉ / REJETÉ
    score_similarite = Column(Float, nullable=True)
    canonique        = Column(Boolean, nullable=False, default=False)
    nb_retries       = Column(Integer, nullable=False, default=0)
    occurence        = Column(Integer, nullable=False, default=0)
    erreur           = Column(Text, nullable=True)
    created_at       = Column(DateTime(timezone=True), server_default=func.now())
    processed_at     = Column(DateTime(timezone=True), nullable=True)
    # Clôture par l'utilisateur (NULL = ouvert). Indépendant de statut_ticket.
    closed_at        = Column(DateTime(timezone=True), nullable=True)

    # Verrou collaboratif (bail à expiration) : évite que deux validateurs
    # traitent le même ticket en même temps. Voir app/api/v1/tickets.py.
    locked_by        = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    locked_at        = Column(DateTime(timezone=True), nullable=True)
    lock_expires_at  = Column(DateTime(timezone=True), nullable=True)

    reponses         = relationship("Reponse", back_populates="ticket")
    user             = relationship("User", foreign_keys=[user_id])
    locker           = relationship("User", foreign_keys=[locked_by])
