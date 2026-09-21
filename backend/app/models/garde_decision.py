import uuid

from sqlalchemy import Boolean, Column, DateTime, Float, String, Text, func
from sqlalchemy.dialects.postgresql import UUID

from app.database import Base


class GardeDecision(Base):
    """Piste d'audit append-only, sans clé étrangère — survit à la suppression de ce qu'elle décrit."""

    __tablename__ = "garde_decisions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    job_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    ticket_id = Column(UUID(as_uuid=True), nullable=True, index=True)  # nul pour une question neuve (ticket créé après)
    domaine = Column(String(50), nullable=True)
    est_suivi = Column(Boolean, nullable=False, default=False)

    # en mode suivi, question_posee est le fil concaténé, pas la seule précision
    question_posee = Column(Text, nullable=False)
    question_indexee = Column(Text, nullable=False)

    reponse_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    score_cosinus = Column(Float, nullable=True)  # pur (pré-BM25) pour rester comparable aux anciennes décisions
    score_lexical = Column(Float, nullable=True)  # les deux colonnes permettent de relire par quelle porte le candidat

    verdict = Column(Boolean, nullable=False, index=True)
    court_circuit = Column(Boolean, nullable=False, default=False)  # True = questions typographiquement identiques
    modele = Column(String(120), nullable=True)  # nul en cas de court-circuit
    erreur = Column(Text, nullable=True)  # non nul = refus faute de joindre Albert, pas un jugement
