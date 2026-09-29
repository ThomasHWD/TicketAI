import json as _json
import os
import uuid as _uuid
from datetime import datetime, timedelta, timezone
from typing import Annotated
from uuid import UUID

import redis as redis_lib
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.core.security import AdminUser
from app.database import get_db
from app.models.ticket import Ticket
from app.schemas.admin import IncidentsResponse, TicketIncident
from app.services.admin_service import scan_document_incidents

router = APIRouter()

DB = Annotated[Session, Depends(get_db)]


@router.get("/incidents", response_model=IncidentsResponse)
def get_incidents(_: AdminUser, db: DB) -> IncidentsResponse:
    echoues = db.query(Ticket).filter(Ticket.statut_job == "ÉCHOUÉ").order_by(Ticket.created_at.desc()).limit(50).all()

    seuil = datetime.now(timezone.utc) - timedelta(minutes=10)
    bloques = (
        db.query(Ticket)
        .filter(Ticket.statut_job == "EN_COURS", Ticket.created_at < seuil)
        .order_by(Ticket.created_at.desc())
        .limit(50)
        .all()
    )

    def _serialize(t: Ticket) -> TicketIncident:
        return TicketIncident(
            id=str(t.id),
            question=t.question,
            domaine=t.domaine,
            statut_job=t.statut_job,
            erreur=t.erreur,
            created_at=t.created_at.isoformat() if t.created_at else "",
        )

    return IncidentsResponse(
        tickets_echoues=[_serialize(t) for t in echoues],
        tickets_bloques=[_serialize(t) for t in bloques],
        documents_echoues=scan_document_incidents(),
    )


@router.delete("/tickets/{ticket_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_ticket_incident(ticket_id: UUID, _: AdminUser, db: DB):
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if ticket is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket introuvable.")
    if ticket.statut_job not in ("ÉCHOUÉ", "EN_COURS"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Le ticket a le statut {ticket.statut_job} et ne peut pas être supprimé depuis les incidents.",
        )
    db.delete(ticket)
    db.commit()


@router.post("/tickets/{ticket_id}/retry")
def retry_ticket(ticket_id: UUID, _: AdminUser, db: DB):
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if ticket is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket introuvable.")
    if ticket.statut_job not in ("ÉCHOUÉ", "EN_COURS"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Le ticket a le statut {ticket.statut_job} et ne peut pas être relancé.",
        )

    new_job_id = _uuid.uuid4()
    ticket.job_id = new_job_id
    ticket.statut_job = "EN_ATTENTE"
    ticket.erreur = None
    ticket.nb_retries = (ticket.nb_retries or 0) + 1
    db.commit()

    from app.workers.question import question_job

    # Same call as the hourly replay: without retraiter the job took ticket_id for a follow-up — the question was
    # stored as the employee's own précision (ghost SUIVI in the timeline), and without user_id nobody was notified.
    question_job.apply_async(
        args=[ticket.question, ticket.domaine, str(ticket.user_id) if ticket.user_id else None],
        kwargs={"ticket_id": str(ticket.id), "objet": ticket.objet, "retraiter": True},
        task_id=str(new_job_id),
        queue="queue_questions",
    )
    return {"job_id": str(new_job_id)}


@router.post("/documents/reconcile")
def reconcile_documents(_: AdminUser, db: DB):
    """Recrée depuis Qdrant les lignes `documents` manquantes. Idempotent."""
    from app.services.document_backfill import reconcilier_documents

    return reconcilier_documents(db)


@router.get("/documents/{task_id}/download")
def download_document(task_id: str, _: AdminUser):
    try:
        r = redis_lib.from_url(settings.valkey_url, socket_connect_timeout=2)
        raw = r.get(f"celery-task-meta-{task_id}")
        if not raw:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tâche introuvable.")
        meta = _json.loads(raw)
        kwargs = meta.get("kwargs") or {}
        file_path = kwargs.get("file_path")
        filename = kwargs.get("filename", "document")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)) from e

    if not file_path or not os.path.exists(file_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Fichier temporaire introuvable sur le disque.",
        )

    return FileResponse(file_path, filename=filename, media_type="application/octet-stream")


@router.post("/documents/{task_id}/retry")
def retry_document(task_id: str, _: AdminUser):
    try:
        r = redis_lib.from_url(settings.valkey_url, socket_connect_timeout=2)
        raw = r.get(f"celery-task-meta-{task_id}")
        if not raw:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tâche introuvable.")
        meta = _json.loads(raw)
        kwargs = meta.get("kwargs") or {}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)) from e

    file_path = kwargs.get("file_path")
    if not file_path or not os.path.exists(file_path):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Fichier temporaire introuvable — re-uploader le document.",
        )

    from app.workers.ingestion import ingestion_job

    new_task_id = str(_uuid.uuid4())
    ingestion_job.apply_async(kwargs=kwargs, task_id=new_task_id, queue="queue_ingestion")

    r.delete(f"celery-task-meta-{task_id}")
    return {"task_id": new_task_id}


@router.delete("/documents/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document_incident(task_id: str, _: AdminUser):
    try:
        r = redis_lib.from_url(settings.valkey_url, socket_connect_timeout=2)
        raw = r.get(f"celery-task-meta-{task_id}")
        if not raw:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tâche introuvable.")
        meta = _json.loads(raw)
        kwargs = meta.get("kwargs") or {}
        file_path = kwargs.get("file_path")
        if file_path and os.path.exists(file_path):
            os.remove(file_path)
        r.delete(f"celery-task-meta-{task_id}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)) from e
