import uuid
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
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
        raise HTTPException(
            400,
            f"Domaine invalide : {payload.domaine}. Valeurs acceptées : {DOMAINES_VALIDES}",
        )

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
    from celery.result import AsyncResult
    from app.workers.celery_app import celery_app

    result = AsyncResult(job_id, app=celery_app)
    reponse = {
        "job_id": job_id,
        "statut": result.status,
    }

    if result.status == "SUCCESS":
        reponse["resultat"] = result.result
    elif result.status == "FAILURE":
        reponse["erreur"] = str(result.result)

    return reponse
