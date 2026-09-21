"""Étage 1 du pipeline de révérification : collecte des réponses candidates (citantes + voisines)."""

import logging
import uuid
from dataclasses import dataclass

from app.models.reponse import Reponse
from app.models.ticket import Ticket
from app.services.embedding import embed_texts
from app.services.obsolescence import (
    Unite,
    fermeture_copies,
    racines,
    reponses_obsoletes,
)
from app.services.qdrant import COLLECTION_NAME, client
from qdrant_client.models import (
    FieldCondition,
    Filter,
    IsEmptyCondition,
    MatchValue,
    PayloadField,
)
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

TOP_K_UNITE = 20

# Low: embedding decides nothing, it widens; reranker filters behind it.
SEUIL_RAPPEL = 0.35


@dataclass
class Candidate:
    """Une réponse à juger, et ce qu'on sait déjà d'elle avant de la juger."""

    reponse: Reponse
    question: str
    citante: bool  # cite au moins un chunk du document modifié — conditionne la sévérité max (voir `decider`)
    prioritaire: bool = False  # cite un chunk disparu — signal factuel qui court-circuite le filtre de pertinence

    @property
    def texte(self) -> str:
        return self.reponse.contenu_corrige or self.reponse.contenu or ""

    def _cle_tri(self) -> tuple:
        return (self.prioritaire, self.citante, self.reponse.canonique, self.reponse.nb_validations or 0)


def rassembler_candidates(
    db: Session,
    doc_id: str,
    domaine: str,
    unites: list[Unite],
    indices_disparus: set[int],
) -> list[Candidate]:
    """Réponses susceptibles d'être touchées, les plus exposées d'abord. Sort order = LLM budget order: prioritaires"""
    citantes = reponses_obsoletes(db, doc_id, indices=None)
    ids_citantes = {r.id for r in citantes}

    ids_prioritaires: set[uuid.UUID] = set()
    if indices_disparus:
        ids_prioritaires = {r.id for r in reponses_obsoletes(db, doc_id, indices=indices_disparus)}

    voisines = [r for r in _voisines(db, domaine, unites) if r.id not in ids_citantes]

    distinctes = racines(citantes + voisines)
    questions = questions_des_reponses(db, distinctes)
    candidates = [
        Candidate(
            reponse=r,
            question=questions.get(r.id, ""),
            citante=r.id in ids_citantes,
            prioritaire=r.id in ids_prioritaires,
        )
        for r in distinctes
    ]

    candidates.sort(key=Candidate._cle_tri, reverse=True)
    return candidates


def _voisines(db: Session, domaine: str, unites: list[Unite]) -> list[Reponse]:
    """Validated domain responses whose question resembles a change unit. Dense-only — lexical paragraph↔question"""
    if not unites:
        return []

    try:
        embeddings = embed_texts([u.texte for u in unites], is_query=True)
    except Exception as exc:
        logger.warning("embedding des changements indisponible (%s) — rappel limité aux citantes", exc)
        return []

    filtre = Filter(
        must=[FieldCondition(key="domaine", match=MatchValue(value=domaine))],
        must_not=[IsEmptyCondition(is_empty=PayloadField(key="reponse_id"))],
    )

    trouves: set[uuid.UUID] = set()
    for emb in embeddings:
        try:
            res = client.query_points(
                collection_name=COLLECTION_NAME,
                query=emb["dense"],
                using="dense",
                query_filter=filtre,
                limit=TOP_K_UNITE,
                with_payload=["reponse_id"],
            )
        except Exception as exc:
            logger.warning("rappel Qdrant impossible (%s)", exc)
            return []
        for point in res.points:
            if point.score < SEUIL_RAPPEL:
                continue
            brut = (point.payload or {}).get("reponse_id")
            if brut:
                try:
                    trouves.add(uuid.UUID(str(brut)))
                except ValueError:
                    continue

    if not trouves:
        return []

    # fermeture_copies: a SUGGESTION/CANONIQUE copy has no Qdrant point of its own — withdrawing only the root leaves
    return (
        db.query(Reponse)
        .filter(
            Reponse.id.in_(fermeture_copies(db, trouves)),
            Reponse.statut == "VALIDÉE",
            Reponse.obsolete.is_(False),
        )
        .all()
    )


def questions_des_reponses(db: Session, reponses: list[Reponse]) -> dict[uuid.UUID, str]:
    """La question à laquelle chaque réponse répond. Public: confrontation.py builds its candidates from a"""
    ids = {r.ticket_id for r in reponses if r.ticket_id is not None}
    tickets = {t.id: t.question for t in db.query(Ticket).filter(Ticket.id.in_(ids)).all()} if ids else {}
    return {r.id: r.question_suivi or tickets.get(r.ticket_id, "") for r in reponses}
