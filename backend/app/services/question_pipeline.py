"""Pipeline RAG : fonctions métier extraites de workers/question.py.

Aucun décorateur Celery ici : ce module est importé par le worker,
et non l'inverse, pour briser la dépendance circulaire.
"""

import logging
import uuid
from datetime import datetime, timezone

from app.config import settings
from app.crud.question import TicketDisparu, upsert_reponse, upsert_ticket  # noqa: F401 — ré-exportés
from app.database import SessionLocal
from app.models.garde_decision import GardeDecision
from app.models.notification import Notification
from app.models.reponse import Reponse
from app.models.ticket import Ticket
from app.services.broadcast import broadcast_sync
from app.services.garde_cache import Decision
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

SEUIL_COSINUS = settings.seuil_cosinus
SEUIL_SUGGESTION = SEUIL_COSINUS - 0.05


def ticket_existe(ticket_id: uuid.UUID) -> bool:
    """Session courte et dédiée : on interroge avant d'ouvrir le pipeline."""
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
) -> None:
    """Consigne une décision du garde dans `garde_decisions`.

    Session dédiée, et non celle du pipeline : la trace doit survivre à l'échec
    de la question qui l'a produite. Un `verdict=True` autorise un service sans
    revue humaine — c'est la seule ligne qui permette d'auditer après coup une
    réponse que personne n'a relue.

    Ne lève jamais : un journal d'audit indisponible ne doit pas faire échouer
    une question.
    """
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
    """Reconstitue le fil d'un ticket pour contextualiser une précision.

    Renvoie :
      - `historique` : messages alternés {"role", "content"} des tours passés,
        prêts à être passés au LLM ;
      - `requete_recherche` : concaténation des intentions utilisateur pour la
        recherche/rerank.
    """
    db = SessionLocal()
    try:
        ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
        if ticket is None:
            return [], precision

        reponses = db.query(Reponse).filter(Reponse.ticket_id == ticket_id).order_by(Reponse.created_at.asc()).all()

        historique: list[dict] = []
        questions_utilisateur: list[str] = [ticket.question]
        premier = True
        for r in reponses:
            if premier:
                historique.append({"role": "user", "content": ticket.question})
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


def trouver_reponse_reutilisable(
    db: Session, chunks: list[dict]
) -> tuple[Reponse | None, float | None, str | None]:
    """Cherche, parmi les chunks, une réponse VALIDÉE réutilisable au-dessus de SEUIL_SUGGESTION.

    Plusieurs réponses validées peuvent matcher → on retient le meilleur score par
    `reponse_id`, puis on choisit de façon déterministe (canonique, plus validée,
    meilleur score, id).

    Renvoie `(reponse, score, question_indexee)` ou `(None, None, None)`.
    `question_indexee` est la question portée par le **point qui a matché** — une
    réponse en a une par formulation validée. Elle vaut `None` pour les points
    écrits avant l'introduction des formulations multiples ; l'appelant retombe
    alors sur `Ticket.question`.
    """
    scores_par_reponse: dict[str, float] = {}
    questions_par_reponse: dict[str, str | None] = {}
    for c in chunks:
        rid = c.get("reponse_id")
        if rid and c["score_cosinus"] >= SEUIL_SUGGESTION:
            rid = str(rid)
            if c["score_cosinus"] > scores_par_reponse.get(rid, -1.0):
                questions_par_reponse[rid] = c.get("question_indexee")
            scores_par_reponse[rid] = max(scores_par_reponse.get(rid, 0.0), c["score_cosinus"])

    if not scores_par_reponse:
        return None, None, None

    candidats = (
        db.query(Reponse)
        .filter(
            Reponse.id.in_([uuid.UUID(r) for r in scores_par_reponse]),
            Reponse.statut == "VALIDÉE",
            Reponse.obsolete.is_(False),
        )
        .all()
    )
    if not candidats:
        return None, None, None

    reponse_liee = max(
        candidats,
        key=lambda r: (
            r.canonique,
            r.nb_validations,
            scores_par_reponse[str(r.id)],
            str(r.id),
        ),
    )
    cle = str(reponse_liee.id)
    return reponse_liee, scores_par_reponse[cle], questions_par_reponse.get(cle)


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
) -> dict:
    """Persiste et renvoie la réutilisation d'une réponse validée.

    `autoriser_canonique` : n'autorise la branche CANONIQUE (servie sans revue
    humaine) que si le match provient de la question/précision BRUTE. Un match
    obtenu par contextualisation du fil ressort toujours en SUGGESTION.
    """
    contenu = reponse_liee.contenu_corrige or reponse_liee.contenu

    if autoriser_canonique and reponse_liee.canonique and score_liee >= SEUIL_COSINUS:
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
