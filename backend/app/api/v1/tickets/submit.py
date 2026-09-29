import uuid

from celery.result import AsyncResult
from fastapi import APIRouter, Body, HTTPException

from app.config import settings
from app.core.permissions import check_ticket_read, user_domaines
from app.core.rate_limit import limiter
from app.core.security import CurrentUser
from app.database import SessionLocal
from app.models.groupe import Groupe
from app.models.reponse import Reponse
from app.models.ticket import Ticket
from app.schemas.ticket import CloturerRequest, QuestionRequest, SuiviRequest
from app.services.broadcast import broadcast_async
from app.workers.celery_app import celery_app
from app.workers.question import question_job

router = APIRouter()

_CLOTURE_BODY = Body(default_factory=CloturerRequest)


@router.get("/tickets/domaines")
async def list_domaines(_: CurrentUser):
    """Liste les domaines disponibles (tout utilisateur authentifié)."""
    db = SessionLocal()
    try:
        rows = db.query(Groupe.domaine).distinct().order_by(Groupe.domaine).all()
        return [r[0] for r in rows]
    finally:
        db.close()


@router.post("/tickets")
async def soumettre_question(payload: QuestionRequest, current_user: CurrentUser):
    limiter("ticket_jour", str(current_user.id), settings.ticket_rate_limit_par_jour, fenetre_secondes=86400)
    domaine = payload.domaine.upper()
    db = SessionLocal()
    try:
        domaines_valides = {r[0] for r in db.query(Groupe.domaine).distinct().all()}
    finally:
        db.close()
    if not domaines_valides:
        raise HTTPException(400, "Aucun domaine configuré. Contactez un administrateur.")
    if domaine not in domaines_valides:
        raise HTTPException(400, f"Domaine invalide : {domaine}")
    if not payload.question.strip():
        raise HTTPException(400, "La question ne peut pas être vide")

    job = question_job.apply_async(
        args=[payload.question, domaine, str(current_user.id)],
        kwargs={"objet": payload.objet},
        queue="queue_questions",
    )

    return {
        "job_id": job.id,
        "question": payload.question,
        "domaine": domaine,
        "statut": "EN_ATTENTE",
    }


@router.post("/tickets/{ticket_id}/suivi")
async def soumettre_suivi(
    ticket_id: str,
    payload: SuiviRequest,
    current_user: CurrentUser,
):
    """Ajoute une précision au fil du ticket : relance le pipeline RAG."""
    if not payload.question.strip():
        raise HTTPException(400, "La question ne peut pas être vide")
    from app.services.ticket_service import parse_ticket_id

    tid = parse_ticket_id(ticket_id)
    db = SessionLocal()
    try:
        ticket = db.query(Ticket).filter(Ticket.id == tid).first()
        if not ticket:
            raise HTTPException(404, "Ticket introuvable")
        if ticket.user_id != current_user.id:
            raise HTTPException(403, "Vous ne pouvez ajouter une précision qu'à vos propres tickets.")
        if ticket.closed_at is not None:
            raise HTTPException(409, "Ticket clôturé : impossible d'ajouter une précision")
        domaine = ticket.domaine
        user_id = str(current_user.id)
        ticket.statut_job = "EN_ATTENTE"
        db.commit()
    finally:
        db.close()

    job = question_job.apply_async(
        args=[payload.question, domaine, user_id],
        kwargs={"ticket_id": ticket_id},
        queue="queue_questions",
    )
    await broadcast_async(f"sse:domain:{domaine}", "ticket_followup", {"ticket_id": ticket_id, "domaine": domaine})
    return {
        "job_id": job.id,
        "ticket_id": ticket_id,
        "question": payload.question,
        "domaine": domaine,
        "statut": "EN_ATTENTE",
    }


@router.post("/tickets/{ticket_id}/cloturer")
async def cloturer_ticket(
    ticket_id: str,
    current_user: CurrentUser,
    payload: CloturerRequest = _CLOTURE_BODY,
):
    """Clôture le ticket. Idempotence refusée : un ticket déjà clôturé renvoie 409."""
    from datetime import datetime, timezone

    from app.services.ticket_service import parse_ticket_id, serialize_ticket

    tid = parse_ticket_id(ticket_id)
    db = SessionLocal()
    try:
        ticket = db.query(Ticket).filter(Ticket.id == tid).first()
        if not ticket:
            raise HTTPException(404, "Ticket introuvable")
        if ticket.user_id != current_user.id:
            raise HTTPException(403, "Seul le créateur du ticket peut le clôturer.")
        if ticket.closed_at is not None:
            raise HTTPException(409, "Ticket déjà clôturé")
        domaine = ticket.domaine
        ticket.closed_at = datetime.now(timezone.utc)
        if payload.note_qualite is not None:
            ticket.note_qualite = payload.note_qualite
        if payload.note_delai is not None:
            ticket.note_delai = payload.note_delai
        db.commit()
        db.refresh(ticket)
        result = serialize_ticket(ticket)
    finally:
        db.close()
    await broadcast_async(f"sse:domain:{domaine}", "ticket_closed", {"ticket_id": ticket_id, "domaine": domaine})
    return result


def _texte_lisible(db, ticket: Ticket, job_result: dict, current_user) -> str | None:
    """The job's answer, as /tickets/{id}/reponses would show it: unreviewed or rejected text stays with reviewers.
    The job result is frozen at generation — the served text is read from the row (a correction replaces it)."""
    rid = job_result.get("reponse_id")
    ligne = db.query(Reponse).filter(Reponse.id == uuid.UUID(rid)).first() if rid else None
    relecteur = current_user.role == "ADMIN" or ticket.domaine in user_domaines(current_user)
    if ligne is None:
        return job_result.get("reponse") if relecteur else None
    if not relecteur and ligne.statut not in ("VALIDÉE", "CORRIGÉE"):
        return None
    return ligne.contenu_corrige or ligne.contenu


@router.get("/tickets/{job_id}/status")
async def statut_ticket(job_id: str, current_user: CurrentUser):
    result = AsyncResult(job_id, app=celery_app)

    reponse = {
        "job_id": job_id,
        "statut_job": result.status,
    }

    if result.status == "SUCCESS":
        job_result = result.result

        reponse["branche"] = job_result.get("branche")
        reponse["question"] = job_result.get("question")
        reponse["domaine"] = job_result.get("domaine")
        reponse["reponse"] = None

        ticket_id = job_result.get("ticket_id")
        if ticket_id:
            db = SessionLocal()
            try:
                ticket = db.query(Ticket).filter(Ticket.id == uuid.UUID(ticket_id)).first()
                if ticket:
                    check_ticket_read(ticket, current_user)
                    reponse["statut_ticket"] = ticket.statut_ticket
                    reponse["ticket_id"] = ticket_id
                    reponse["reponse"] = _texte_lisible(db, ticket, job_result, current_user)
            finally:
                db.close()

    elif result.status == "FAILURE":
        reponse["erreur"] = str(result.result)

    return reponse
