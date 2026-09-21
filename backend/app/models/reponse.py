import uuid

from sqlalchemy import JSON, Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.database import Base


class Reponse(Base):
    __tablename__ = "reponses"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ticket_id = Column(UUID(as_uuid=True), ForeignKey("tickets.id"), nullable=False)
    contenu = Column(Text, nullable=False)
    statut = Column(String(20), nullable=False, default="EN_ATTENTE")
    # EN_ATTENTE / VALIDÉE / REJETÉE / CORRIGÉE
    source = Column(String(20), nullable=False)  # LLM | CANONIQUE | SUGGESTION | HORS_DOMAINE
    nb_validations = Column(Integer, nullable=False, default=0)
    canonique = Column(Boolean, nullable=False, default=False)
    reponse_source_id = Column(UUID(as_uuid=True), ForeignKey("reponses.id"), nullable=True)
    contenu_corrige = Column(Text, nullable=True)
    correction_suggeree = Column(Text, nullable=True)
    passages_pertinents = Column(JSON, nullable=True)  # {"ajoutes": [...], "retires": [...]} ou null
    question_suivi = Column(Text, nullable=True)  # null pour la réponse à la question initiale
    chunks = relationship("ReponseChunk", back_populates="reponse")
    score_similarite = Column(Float, nullable=True)
    validator_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    validated_at = Column(DateTime(timezone=True), nullable=True)
    raison_rejet = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # seul un validateur/gestionnaire peut exposer une réponse dans la FAQ
    faq_visible = Column(Boolean, nullable=False, default=False, server_default="false")

    # drapeau, pas une valeur de statut — évite de réécrire l'historique des tickets clos
    obsolete = Column(Boolean, nullable=False, default=False, server_default="false", index=True)
    obsolete_raison = Column(String(30), nullable=True)  # DOC_MIS_A_JOUR | DOC_SUPPRIMÉ
    obsolete_doc_id = Column(String, nullable=True)
    obsolete_version = Column(Integer, nullable=True)
    obsolete_at = Column(DateTime(timezone=True), nullable=True)

    # file de relecture, pas un retrait — la réponse reste servie ; ANALYSE_EN_COURS est le seul état transitoire
    a_relire = Column(Boolean, nullable=False, default=False, server_default="false", index=True)
    a_relire_raison = Column(String(30), nullable=True)  # cf. RAISON_* dans services/obsolescence.py
    a_relire_doc_id = Column(String, nullable=True)
    a_relire_version = Column(Integer, nullable=True)
    a_relire_at = Column(DateTime(timezone=True), nullable=True)

    # effacé uniquement par INTACTE — lever_a_relire seul ne suffit pas
    analyse_justification = Column(Text, nullable=True)
    analyse_extraits = Column(JSON, nullable=True)  # unités figées ; l'archive de la version sortante peut être purgée

    tag = Column(String(100), nullable=True)

    ticket = relationship("Ticket", back_populates="reponses")
    validator = relationship("User", foreign_keys=[validator_id])
