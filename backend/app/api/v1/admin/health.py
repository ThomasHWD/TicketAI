import json as _json
import os
import uuid as _uuid
from datetime import datetime, timedelta, timezone
from typing import Annotated
from uuid import UUID

import redis as redis_lib
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings
from app.core.security import AdminUser, CurrentUser
from app.database import SessionLocal
from app.models.document import Document
from app.models.reponse import Reponse
from app.models.site_config import SiteConfig
from app.models.ticket import Ticket
from app.schemas.admin import (
    ConfigPayload,
    FunctionalStats,
    HealthResponse,
    IncidentsResponse,
    ServiceStatus,
    TicketIncident,
)
from app.services.admin_service import (
    _CONFIG_DEFAULTS,
    celery_status_and_count,
    ping_albert,
    scan_document_incidents,
)
from app.services.broadcast import broadcast_sync

router = APIRouter()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


DB = Annotated[Session, Depends(get_db)]


@router.get("/health", response_model=HealthResponse)
def get_health(_: AdminUser, db: DB) -> HealthResponse:
    try:
        db.execute(text("SELECT 1"))
        pg = ServiceStatus(status="ok")
    except Exception as e:
        pg = ServiceStatus(status="error", detail=str(e))

    try:
        from app.services.qdrant import client as qdrant_client

        qdrant_client.get_collections()
        qd = ServiceStatus(status="ok")
    except Exception as e:
        qd = ServiceStatus(status="error", detail=str(e))

    try:
        r = redis_lib.from_url(settings.valkey_url, socket_connect_timeout=2)
        r.ping()
        vk = ServiceStatus(status="ok")
    except Exception as e:
        vk = ServiceStatus(status="error", detail=str(e))

    al_emb = ping_albert(settings.albert_embeddings_url, settings.albert_api_key)
    al_llm = ping_albert(settings.albert_llm_url, settings.albert_api_key)
    al_rer = ping_albert(settings.albert_reranker_url, settings.albert_api_key)

    celery_queues_info: dict = {}
    try:
        from app.workers.celery_app import celery_app

        inspector = celery_app.control.inspect(timeout=2)
        celery_queues_info = inspector.active_queues() or {}
    except Exception:
        pass

    cel_ing, workers_ing = celery_status_and_count("queue_ingestion", celery_queues_info)
    cel_q, workers_q = celery_status_and_count("queue_questions", celery_queues_info)

    cel_beat = ServiceStatus(status="error", detail="Beat non démarré")
    try:
        from app.workers.auto_cloture import BEAT_HEARTBEAT_KEY, BEAT_STARTED_KEY
        r_beat = redis_lib.from_url(settings.valkey_url, socket_connect_timeout=2)
        if r_beat.get(BEAT_HEARTBEAT_KEY):
            cel_beat = ServiceStatus(status="ok")
        elif r_beat.get(BEAT_STARTED_KEY):
            cel_beat = ServiceStatus(status="ok", detail="Démarré, en attente de la première exécution (02h00)")
    except Exception as e:
        cel_beat = ServiceStatus(status="error", detail=str(e))

    nb_documents = db.query(Document).filter(Document.statut != "SUPPRIMÉ").count()
    nb_reponses_validees = db.query(Reponse).filter(Reponse.canonique).count()
    reponses_a_relire = db.query(Reponse).filter(Reponse.a_relire).count()
    tickets_echoues = db.query(Ticket).filter(Ticket.statut_job == "ÉCHOUÉ").count()
    seuil = datetime.now(timezone.utc) - timedelta(minutes=10)
    tickets_bloques = db.query(Ticket).filter(Ticket.statut_job == "EN_COURS", Ticket.created_at < seuil).count()

    celery_pending_ingestion: int | None = None
    celery_pending_questions: int | None = None
    documents_echoues = 0
    try:
        r = redis_lib.from_url(settings.valkey_url, socket_connect_timeout=2)
        celery_pending_ingestion = r.llen("queue_ingestion")
        celery_pending_questions = r.llen("queue_questions")
        for key in r.scan_iter("celery-task-meta-*", count=200):
            raw = r.get(key)
            if raw:
                try:
                    meta = _json.loads(raw)
                    if meta.get("status") == "FAILURE" and "ingestion_job" in str(
                        meta.get("task_name") or meta.get("name") or ""
                    ):
                        documents_echoues += 1
                except Exception:
                    pass
    except Exception:
        pass

    derniere_activite: str | None = None
    last = (
        db.query(Ticket.processed_at)
        .filter(Ticket.processed_at.isnot(None))
        .order_by(Ticket.processed_at.desc())
        .first()
    )
    if last and last[0]:
        derniere_activite = last[0].isoformat()

    return HealthResponse(
        postgres=pg,
        qdrant=qd,
        valkey=vk,
        albert_embeddings=al_emb,
        albert_llm=al_llm,
        albert_reranker=al_rer,
        celery_ingestion=cel_ing,
        celery_questions=cel_q,
        celery_beat=cel_beat,
        stats=FunctionalStats(
            nb_documents=nb_documents,
            nb_reponses_validees=nb_reponses_validees,
            reponses_a_relire=reponses_a_relire,
            tickets_echoues=tickets_echoues,
            tickets_bloques=tickets_bloques,
            documents_echoues=documents_echoues,
            celery_pending_ingestion=celery_pending_ingestion,
            celery_pending_questions=celery_pending_questions,
            celery_workers_ingestion=workers_ing,
            celery_workers_questions=workers_q,
            derniere_activite=derniere_activite,
        ),
    )


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

    question_job.apply_async(
        kwargs={"ticket_id": str(ticket.id), "question": ticket.question, "domaine": ticket.domaine},
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


@router.get("/config")
def get_config(current_user: CurrentUser, db: DB):
    """Retourne la configuration du site (tout utilisateur authentifié)."""
    rows = db.query(SiteConfig).all()
    result = dict(_CONFIG_DEFAULTS)
    for row in rows:
        result[row.key] = row.value
    result["jours_auto_cloture"] = settings.jours_auto_cloture
    return result


@router.put("/config/{key}")
def set_config(key: str, body: ConfigPayload, _: AdminUser, db: DB):
    """Met à jour une clé de configuration (admin uniquement)."""
    if key not in _CONFIG_DEFAULTS:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Clé de configuration inconnue : {key}")
    row = db.query(SiteConfig).filter(SiteConfig.key == key).first()
    if row is None:
        row = SiteConfig(key=key, value=body.value)
        db.add(row)
    else:
        row.value = body.value
    db.commit()
    db.refresh(row)
    if key == "banner":
        broadcast_sync("sse:global", "banner_updated", {})
    return {"key": row.key, "value": row.value}
