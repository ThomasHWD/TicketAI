import uuid

from celery.result import AsyncResult
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.database import SessionLocal
from app.models.ticket import Ticket
from app.workers.celery_app import celery_app
from app.workers.question import question_job

router = APIRouter()

DOMAINES_VALIDES = {"IT", "RH", "JURIDIQUE"}


class QuestionRequest(BaseModel):
    question: str
    domaine: str
    user_id: str | None = None


@router.post("/tickets")
async def soumettre_question(payload: QuestionRequest):
    if payload.domaine.upper() not in DOMAINES_VALIDES:
        raise HTTPException(400, f"Domaine invalide : {payload.domaine}")
    if not payload.question.strip():
        raise HTTPException(400, "La question ne peut pas être vide")

    job = question_job.apply_async(
        args=[payload.question, payload.domaine.upper(), payload.user_id],
        queue="queue_questions",
    )

    return {
        "job_id": job.id,
        "question": payload.question,
        "domaine": payload.domaine.upper(),
        "statut": "EN_ATTENTE",
    }


@router.get("/tickets")
async def liste_tickets(
    page: int = 1,
    limit: int = 10,
    domaine: str | None = None,
    statut: str | None = None,
):
    db = SessionLocal()
    try:
        query = db.query(Ticket)
        if domaine:
            query = query.filter(Ticket.domaine == domaine.upper())
        if statut:
            query = query.filter(Ticket.statut_ticket == statut.upper())
        total = query.count()
        tickets = (
            query.order_by(Ticket.created_at.desc())
            .offset((page - 1) * limit)
            .limit(limit)
            .all()
        )
        return {
            "total": total,
            "page": page,
            "limit": limit,
            "items": [
                {
                    "id": str(t.id),
                    "question": t.question,
                    "domaine": t.domaine,
                    "statut_ticket": t.statut_ticket,
                    "statut_job": t.statut_job,
                    "user_id": str(t.user_id) if t.user_id else None,
                    "user_email": t.user.email if t.user else None,
                    "canonique": t.canonique,
                    "created_at": t.created_at.isoformat() if t.created_at else None,
                }
                for t in tickets
            ],
        }
    finally:
        db.close()


@router.get("/tickets/{ticket_id}/reponses")
async def reponses_par_ticket(ticket_id: str):
    from app.models.reponse import Reponse as ReponseModel
    db = SessionLocal()
    try:
        try:
            tid = uuid.UUID(ticket_id)
        except ValueError:
            raise HTTPException(400, "ticket_id invalide")
        ticket = db.query(Ticket).filter(Ticket.id == tid).first()
        if not ticket:
            raise HTTPException(404, "Ticket introuvable")
        reponses = (
            db.query(ReponseModel)
            .filter(ReponseModel.ticket_id == tid)
            .order_by(ReponseModel.created_at.asc())
            .all()
        )
        return [
            {
                "id": str(r.id),
                "ticket_id": str(r.ticket_id),
                "contenu": r.contenu,
                "statut": r.statut,
                "source": r.source,
                "nb_validations": r.nb_validations,
                "canonique": r.canonique,
                "score_similarite": r.score_similarite,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in reponses
        ]
    finally:
        db.close()


@router.get("/tickets/{ticket_id}")
async def get_ticket(ticket_id: str):
    db = SessionLocal()
    try:
        try:
            tid = uuid.UUID(ticket_id)
        except ValueError:
            raise HTTPException(400, "ticket_id invalide")
        ticket = db.query(Ticket).filter(Ticket.id == tid).first()
        if not ticket:
            raise HTTPException(404, "Ticket introuvable")
        return {
            "id": str(ticket.id),
            "question": ticket.question,
            "domaine": ticket.domaine,
            "statut_ticket": ticket.statut_ticket,
            "statut_job": ticket.statut_job,
            "user_id": str(ticket.user_id) if ticket.user_id else None,
            "user_email": ticket.user.email if ticket.user else None,
            "canonique": ticket.canonique,
            "created_at": ticket.created_at.isoformat() if ticket.created_at else None,
        }
    finally:
        db.close()


@router.get("/tickets/{job_id}/status")
async def statut_ticket(job_id: str):
    # Statut Celery
    result = AsyncResult(job_id, app=celery_app)

    reponse = {
        "job_id": job_id,
        "statut_job": result.status,
    }

    # Si le job est terminé, enrichit avec les données PostgreSQL
    if result.status == "SUCCESS":
        job_result = result.result

        reponse["branche"] = job_result.get("branche")
        reponse["question"] = job_result.get("question")
        reponse["domaine"] = job_result.get("domaine")
        reponse["reponse"] = job_result.get("reponse")

        # Récupère le statut métier depuis PostgreSQL
        ticket_id = job_result.get("ticket_id")
        if ticket_id:
            db = SessionLocal()
            try:
                ticket = (
                    db.query(Ticket).filter(Ticket.id == uuid.UUID(ticket_id)).first()
                )
                if ticket:
                    reponse["statut_ticket"] = ticket.statut_ticket
                    reponse["ticket_id"] = ticket_id
            finally:
                db.close()

    elif result.status == "FAILURE":
        reponse["erreur"] = str(result.result)

    return reponse
