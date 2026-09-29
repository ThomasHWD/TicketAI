"""RAG pipeline: business logic extracted from workers/question.py. No Celery decorators here — this module is"""

import logging
import uuid
from datetime import datetime, timezone
from typing import NamedTuple

from app.config import settings
from app.crud.question import TicketDisparu, upsert_reponse, upsert_ticket  # noqa: F401 — re-exported
from app.database import SessionLocal
from app.models.garde_decision import GardeDecision
from app.models.notification import Notification
from app.models.reponse import Reponse
from app.models.ticket import Ticket
from app.services.broadcast import broadcast_sync
from app.services.garde_cache import Decision
from app.services.search import franchit_le_rappel
from sqlalchemy import or_
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

SEUIL_COSINUS = settings.seuil_cosinus
SEUIL_SUGGESTION = SEUIL_COSINUS - 0.05


def peut_servir_sans_revue(reponse: Reponse) -> bool:
    """a_relire is triage not withdrawal — SQL mirror in services/faq.py must agree; a test compares them on the"""
    return bool(reponse.canonique) and not reponse.a_relire


def ticket_existe(ticket_id: uuid.UUID) -> bool:
    """Short dedicated session — checked before opening the full pipeline."""
    db = SessionLocal()
    try:
        return db.query(Ticket.id).filter(Ticket.id == ticket_id).first() is not None
    finally:
        db.close()


def journaliser_garde(
    decision: Decision,
    *,
    job_id: uuid.UUID | None,
    ticket_id: uuid.UUID | None,
    domaine: str | None,
    est_suivi: bool,
    question_posee: str,
    question_indexee: str,
    reponse_id: uuid.UUID | None,
    score_cosinus: float | None,
    score_lexical: float | None = None,
) -> None:
    """Dedicated session — trace survives pipeline failure; verdict=True is the only audit record of unreviewed"""
    db = SessionLocal()
    try:
        db.add(
            GardeDecision(
                job_id=job_id,
                ticket_id=ticket_id,
                domaine=domaine,
                est_suivi=est_suivi,
                question_posee=question_posee,
                question_indexee=question_indexee,
                reponse_id=reponse_id,
                score_cosinus=score_cosinus,
                score_lexical=score_lexical,
                verdict=decision.verdict,
                court_circuit=decision.court_circuit,
                modele=decision.modele,
                erreur=decision.erreur,
            )
        )
        db.commit()
    except Exception as exc:
        logger.warning("Journal du garde indisponible : %s", exc)
        db.rollback()
    finally:
        db.close()


def charger_contexte_fil(ticket_id: uuid.UUID, precision: str) -> tuple[list[dict], str]:
    """Returns (historique, requete_recherche): LLM message history and concatenated user intents for search."""
    db = SessionLocal()
    try:
        ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
        if ticket is None:
            return [], precision

        # Obsolete turns skipped: a withdrawn answer must not seed generation, and a re-processed follow-up's
        # obsolete draft would otherwise put its own question in the thread twice.
        reponses = (
            db.query(Reponse)
            .filter(Reponse.ticket_id == ticket_id, Reponse.obsolete.is_(False))
            .order_by(Reponse.created_at.asc())
            .all()
        )

        historique: list[dict] = []
        questions_utilisateur: list[str] = [ticket.question]
        premier = True
        for r in reponses:
            if premier:
                ouverture = ticket.question
                if r.question_suivi:  # initial turn withdrawn — first surviving turn is a follow-up
                    ouverture += "\n" + r.question_suivi
                    questions_utilisateur.append(r.question_suivi)
                historique.append({"role": "user", "content": ouverture})
                premier = False
            elif r.question_suivi:
                historique.append({"role": "user", "content": r.question_suivi})
                questions_utilisateur.append(r.question_suivi)
            historique.append({"role": "assistant", "content": r.contenu_corrige or r.contenu})

        questions_utilisateur.append(precision)
        requete_recherche = "\n".join(questions_utilisateur)
        return historique, requete_recherche
    finally:
        db.close()


def question_du_point_fiable(db: Session, reponse: Reponse, question_indexee: str) -> bool:
    """False for a follow-up point written before reformulation — indexed under its bare text (« et pour un
    apprenti ? »), the judge compares a thread to an identical context-free question — not a judgeable pair (it
    held NON 3/3 on one measured case, which proves nothing general). Checked on the response and its copies (alias
    points carry the copy's question). scripts/reindexer_suivis.py rewrites them."""
    tours = (
        db.query(Reponse.question_autonome)
        .filter(
            or_(Reponse.id == reponse.id, Reponse.reponse_source_id == reponse.id),
            Reponse.question_suivi == question_indexee,
        )
        .all()
    )
    # a follow-up already self-contained is rewritten verbatim — its stored rewrite vouches for the point
    return all(t.question_autonome == question_indexee for t in tours)


class Candidat(NamedTuple):
    """Two signals kept separate (disjunction); score_cosinus_max is the max across all formulations so servable can"""

    reponse: Reponse | None
    score_cosinus: float | None
    score_lexical: float | None
    question_indexee: str | None
    score_cosinus_max: float | None = None

    def franchit(self, seuil_cosinus: float) -> bool:
        if self.reponse is None:
            return False
        return franchit_le_rappel(
            {"score_cosinus": self.score_cosinus or 0.0, "score_lexical": self.score_lexical or 0.0},
            seuil_cosinus,
        )

    @property
    def servable(self) -> bool:
        """Lexical-only non-canonical candidate → RAG, not SUGGESTION. SUGGESTION has no judge to protect it."""
        cos = self.score_cosinus_max if self.score_cosinus_max is not None else (self.score_cosinus or 0.0)
        return cos >= SEUIL_SUGGESTION


AUCUN_CANDIDAT = Candidat(None, None, None, None)


def trouver_reponse_reutilisable(db: Session, chunks: list[dict]) -> Candidat:
    """Find the best reusable VALIDÉE/CORRIGÉE response. Relevance first (RRF), status as tiebreaker"""
    # single dict per reponse_id: dominant chunk (for question_indexee and lexical), max cosine (for servable).
    meilleur_par_reponse: dict[str, dict] = {}
    for c in chunks:
        rid = c.get("reponse_id")
        if not rid or not franchit_le_rappel(c, SEUIL_SUGGESTION):
            continue
        rid = str(rid)
        cos = c.get("score_cosinus", 0.0)
        if c.get("score_rrf", 0.0) > meilleur_par_reponse.get(rid, {}).get("score_rrf", -1.0):
            meilleur_par_reponse[rid] = c
        # max cosine across all formulations — servable may be True even when BM25-dominant chunk has low cosine.
        if cos > meilleur_par_reponse[rid].get("_score_cosinus_max", 0.0):
            meilleur_par_reponse[rid]["_score_cosinus_max"] = cos

    if not meilleur_par_reponse:
        return AUCUN_CANDIDAT

    candidats = (
        db.query(Reponse)
        .filter(
            Reponse.id.in_([uuid.UUID(r) for r in meilleur_par_reponse]),
            # CORRIGÉE included — excluding it made the "Corriger" gesture sterile (answer indexed but never reused).
            Reponse.statut.in_(("VALIDÉE", "CORRIGÉE")),
            Reponse.obsolete.is_(False),
        )
        .all()
    )
    if not candidats:
        return AUCUN_CANDIDAT

    # Relevance first (RRF), status as tiebreaker — canonical general used to outrank specific validated at higher RRF.
    reponse_liee = max(
        candidats,
        key=lambda r: (
            meilleur_par_reponse[str(r.id)].get("score_rrf", 0.0),
            r.canonique,
            r.nb_validations,
            str(r.id),
        ),
    )
    point = meilleur_par_reponse[str(reponse_liee.id)]
    return Candidat(
        reponse_liee,
        point.get("score_cosinus", 0.0),
        point.get("score_lexical", 0.0),
        point.get("question_indexee"),
        point.get("_score_cosinus_max", point.get("score_cosinus", 0.0)),
    )


def servir_reutilisation(
    db: Session,
    job_id: uuid.UUID,
    ticket_uuid: uuid.UUID | None,
    question: str,
    domaine: str,
    user_uuid: uuid.UUID | None,
    reponse_liee: Reponse,
    score_liee: float,
    question_suivi: str | None,
    est_suivi: bool,
    nb_retries: int,
    autoriser_canonique: bool,
    objet: str | None = None,
    score_lexical: float = 0.0,
) -> dict:
    """Persist and return a validated-response reuse. autoriser_canonique gates CANONIQUE (unreviewed serving)"""
    contenu = reponse_liee.contenu_corrige or reponse_liee.contenu
    franchit = franchit_le_rappel({"score_cosinus": score_liee, "score_lexical": score_lexical}, SEUIL_COSINUS)

    if autoriser_canonique and peut_servir_sans_revue(reponse_liee) and franchit:
        logger.info("Réponse canonique servie : %s (score=%.3f)", reponse_liee.id, score_liee)
        ticket = upsert_ticket(
            db,
            job_id,
            ticket_id=ticket_uuid,
            question=question,
            objet=objet,
            domaine=domaine,
            user_id=user_uuid,
            statut_job="TERMINÉ",
            statut_ticket="RÉPONDU",
            score_similarite=score_liee,
            canonique=True,
            nb_retries=nb_retries,
            erreur=None,
            processed_at=datetime.now(timezone.utc),
        )
        ticket_id_str = str(ticket.id)

        reponse = upsert_reponse(
            db,
            ticket,
            contenu,
            score_liee,
            source="CANONIQUE",
            reponse_source_id=reponse_liee.id,
            statut="VALIDÉE",
            canonique=True,
            question_suivi=question_suivi,
            nouveau=est_suivi,
            tag=reponse_liee.tag,
        )

        ticket_source = db.query(Ticket).filter(Ticket.id == reponse_liee.ticket_id).first()
        if ticket_source:
            ticket_source.occurence += 1

        if ticket.user_id:
            db.add(
                Notification(
                    user_id=ticket.user_id,
                    ticket_id=ticket.id,
                    reponse_id=reponse.id,
                    type="REPONSE_VALIDEE",
                )
            )
        db.commit()

        event = "ticket_followup" if est_suivi else "ticket_answered"
        broadcast_sync(f"sse:domain:{domaine}", event, {"ticket_id": ticket_id_str, "domaine": domaine})
        if ticket.user_id:
            broadcast_sync(f"sse:user:{ticket.user_id}", "notification_created", {"ticket_id": ticket_id_str})

        return {
            "statut": "OK",
            "branche": "CANONIQUE",
            "question": question,
            "domaine": domaine,
            "reponse": contenu,
            "ticket_id": ticket_id_str,
            "reponse_id": str(reponse.id),
            "reponse_source_id": str(reponse_liee.id),
            "top_score_cosinus": score_liee,
        }

    logger.info("Suggestion via réponse validée %s (score=%.3f)", reponse_liee.id, score_liee)
    ticket = upsert_ticket(
        db,
        job_id,
        ticket_id=ticket_uuid,
        question=question,
        objet=objet,
        domaine=domaine,
        user_id=user_uuid,
        statut_job="TERMINÉ",
        statut_ticket="RÉPONDU",
        score_similarite=score_liee,
        canonique=False,
        nb_retries=nb_retries,
        erreur=None,
        processed_at=datetime.now(timezone.utc),
    )
    reponse = upsert_reponse(
        db,
        ticket,
        contenu,
        score_liee,
        source="SUGGESTION",
        reponse_source_id=reponse_liee.id,
        question_suivi=question_suivi,
        nouveau=est_suivi,
        tag=reponse_liee.tag,
    )
    ticket_id_str_sug = str(ticket.id)
    db.commit()

    event = "ticket_followup" if est_suivi else "ticket_answered"
    broadcast_sync(f"sse:domain:{domaine}", event, {"ticket_id": ticket_id_str_sug, "domaine": domaine})
    if user_uuid:
        broadcast_sync(f"sse:user:{user_uuid}", event, {"ticket_id": ticket_id_str_sug, "domaine": domaine})

    return {
        "statut": "OK",
        "branche": "SUGGESTION",
        "question": question,
        "domaine": domaine,
        "reponse": contenu,
        "ticket_id": ticket_id_str_sug,
        "reponse_id": str(reponse.id),
        "reponse_source_id": str(reponse_liee.id),
        "top_score_cosinus": score_liee,
    }
