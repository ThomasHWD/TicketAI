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
    source = Column(String(20), nullable=False)
    # LLM
    nb_validations = Column(Integer, nullable=False, default=0)
    canonique = Column(Boolean, nullable=False, default=False)
    reponse_source_id = Column(UUID(as_uuid=True), ForeignKey("reponses.id"), nullable=True)
    contenu_corrige = Column(Text, nullable=True)
    correction_suggeree = Column(Text, nullable=True)
    # Passages du document retenus par le pré-filtrage sémantique et envoyés au LLM.
    # {"ajoutes": ["...", "..."], "retires": ["..."]} — null si filtre LLM désactivé
    # ou si la réponse a été signalée avant l'introduction de ce champ.
    passages_pertinents = Column(JSON, nullable=True)
    # Texte de la précision (relance utilisateur) ayant déclenché cette réponse.
    # NULL pour la réponse à la question initiale du ticket.
    question_suivi = Column(Text, nullable=True)
    chunks = relationship("ReponseChunk", back_populates="reponse")
    score_similarite = Column(Float, nullable=True)
    validator_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    validated_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Obsolescence : un drapeau, et non une valeur de `statut`. Les copies
    # SUGGESTION/CANONIQUE SONT les réponses affichées sur les tickets des
    # utilisateurs ; écrire OBSOLÈTE dans `statut` afficherait rétroactivement
    # comme périmée une réponse qui a bien été validée et était correcte à
    # l'époque. Le drapeau donne le comportement voulu — retirée de Qdrant,
    # jamais resservie, restaurable — sans réécrire l'historique des tickets clos.
    obsolete = Column(Boolean, nullable=False, default=False, server_default="false", index=True)
    obsolete_raison = Column(String(30), nullable=True)  # DOC_MIS_A_JOUR | DOC_SUPPRIMÉ
    obsolete_doc_id = Column(String, nullable=True)
    obsolete_version = Column(Integer, nullable=True)
    obsolete_at = Column(DateTime(timezone=True), nullable=True)

    # « À relire » : la ré-vérification n'a pas pu conclure — le modèle a hésité,
    # Albert n'a pas répondu, le budget d'appels était épuisé, ou le rapprochement
    # avec le changement est trop indirect pour qu'une machine tranche seule.
    # Contrairement à `obsolete`, la réponse reste indexée et servie : le drapeau
    # est une file de relecture, pas un retrait. ANALYSE_EN_COURS est le seul état
    # transitoire de la colonne — le worker le résout, ou son `on_failure` le rabat.
    a_relire = Column(Boolean, nullable=False, default=False, server_default="false", index=True)
    a_relire_raison = Column(String(30), nullable=True)  # cf. RAISON_* dans services/obsolescence.py
    a_relire_doc_id = Column(String, nullable=True)
    a_relire_version = Column(Integer, nullable=True)
    a_relire_at = Column(DateTime(timezone=True), nullable=True)

    # Trace du verdict de ré-vérification, commune aux deux drapeaux. Sans elle, un
    # retrait sec est une réponse qui disparaît sans que personne sache pourquoi :
    # c'est ce qui rend l'automatisme acceptable plutôt que subi. `lever_a_relire`
    # ne les efface pas — seul le verdict INTACTE le fait, puisqu'il ne reste alors
    # rien à expliquer.
    analyse_justification = Column(Text, nullable=True)
    # Les unités de changement qui ont fondé le verdict, figées : l'archive de la
    # version sortante sera purgée un jour, la justification doit rester lisible.
    # [{"sens": ..., "avant": ..., "apres": ...}]
    analyse_extraits = Column(JSON, nullable=True)

    ticket = relationship("Ticket", back_populates="reponses")
    validator = relationship("User", foreign_keys=[validator_id])
