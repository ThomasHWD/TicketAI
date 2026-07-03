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
