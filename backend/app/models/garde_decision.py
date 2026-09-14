import uuid

from sqlalchemy import Boolean, Column, DateTime, Float, String, Text, func
from sqlalchemy.dialects.postgresql import UUID

from app.database import Base


class GardeDecision(Base):
    """Journal des décisions du garde du cache canonique.

    Le verdict du garde ne laissait aucune trace exploitable : un refus fait
    retomber la question dans le pipeline RAG, et la réponse produite est alors
    indiscernable en base d'un cas sans candidat. Impossible, dès lors, de
    compter les approbations, de mesurer un taux de faux positifs, ou d'auditer
    après coup une réponse servie sans revue humaine.

    Cette table comble ce trou. Elle est en **ajout seul** et volontairement sans
    clé étrangère : c'est une piste d'audit, elle ne doit ni bloquer la
    suppression d'une réponse ni disparaître avec elle. `reponse_id` et
    `ticket_id` sont donc des UUID nus, éventuellement orphelins.

    La ligne qui compte pour la sûreté est `verdict = true` : elle porte la paire
    (question posée, question indexée) qui a autorisé un service sans revue.
    """

    __tablename__ = "garde_decisions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    # Contexte de l'appel. `ticket_id` est nul pour une question neuve : le
    # ticket n'est créé qu'après la décision.
    job_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    ticket_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    domaine = Column(String(50), nullable=True)
    est_suivi = Column(Boolean, nullable=False, default=False)

    # La paire jugée, telle qu'elle a été soumise. En mode suivi,
    # `question_posee` est le fil concaténé, pas la seule précision.
    question_posee = Column(Text, nullable=False)
    question_indexee = Column(Text, nullable=False)

    reponse_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    # Le cosinus **pur**, qui garde exactement le sens qu'il avait avant BM25 :
    # sans quoi les décisions antérieures deviendraient incomparables aux nouvelles.
    score_cosinus = Column(Float, nullable=True)
    # Le second signal, BM25 ramené au terme. La porte se franchit par le cosinus
    # **ou** par lui : sans les deux colonnes, on ne peut pas relire par quelle
    # porte un candidat est passé. Nul avant l'arrivée de la recherche lexicale.
    score_lexical = Column(Float, nullable=True)

    verdict = Column(Boolean, nullable=False, index=True)
    # True quand les deux questions étaient typographiquement identiques :
    # verdict rendu sans appel LLM, donc sans consommer de quota.
    court_circuit = Column(Boolean, nullable=False, default=False)
    # Nul en cas de court-circuit ; sinon le modèle qui a rendu le verdict.
    modele = Column(String(120), nullable=True)
    # Renseigné quand le garde a refusé faute de pouvoir joindre Albert : ce
    # refus-là n'est pas un jugement, il ne doit pas être lu comme tel.
    erreur = Column(Text, nullable=True)
