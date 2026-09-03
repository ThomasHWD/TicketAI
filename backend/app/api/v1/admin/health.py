import json as _json
from datetime import datetime, timedelta, timezone
from typing import Annotated

import httpx
import redis as redis_lib
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings
from app.core.security import AdminUser
from app.database import get_db
from app.models.document import Document
from app.models.reponse import Reponse
from app.models.ticket import Ticket
from app.schemas.admin import (
    AlbertModelUsage,
    AlbertQuotasResponse,
    FunctionalStats,
    HealthResponse,
    ServiceStatus,
)
from app.services.admin_service import celery_status_and_count, ping_albert

router = APIRouter()

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


@router.get("/albert-quotas", response_model=AlbertQuotasResponse)
def get_albert_quotas(_: AdminUser) -> AlbertQuotasResponse:
    base = settings.albert_llm_url
    headers = {"Authorization": f"Bearer {settings.albert_api_key}"}

    info: dict = {}
    try:
        r = httpx.get(f"{base}/me/info", headers=headers, timeout=5.0)
        if r.is_success:
            info = r.json()
    except Exception:
        pass

    now_utc = datetime.now(timezone.utc)
    start_of_today = int(datetime(now_utc.year, now_utc.month, now_utc.day, tzinfo=timezone.utc).timestamp())

    usage_data: list = []
    try:
        PAGE = 100
        offset = 0
        while True:
            r = httpx.get(
                f"{base}/me/usage",
                headers=headers,
                params={"start_time": start_of_today, "limit": PAGE, "offset": offset},
                timeout=10.0,
            )
            if not r.is_success:
                break
            page = r.json().get("data") or []
            usage_data.extend(page)
            if len(page) < PAGE:
                break
            offset += PAGE
    except Exception:
        pass

    limits_raw: list = info.get("limits") or []
    tpd_values = [lim["value"] for lim in limits_raw if lim.get("type") == "tpd" and lim.get("value") is not None]
    rpd_values = [lim["value"] for lim in limits_raw if lim.get("type") == "rpd" and lim.get("value") is not None]
    limite_tpd: int | None = min(tpd_values) if tpd_values else None
    limite_rpd: int | None = min(rpd_values) if rpd_values else None

    today = now_utc.date()
    aggregated: dict[str, dict] = {}
    for event in usage_data:
        created = event.get("created") or 0
        if datetime.fromtimestamp(created, tz=timezone.utc).date() != today:
            continue
        model = event.get("model") or "inconnu"
        if model not in aggregated:
            aggregated[model] = {"tokens": 0, "requests": 0}
        usage_evt = event.get("usage") or {}
        aggregated[model]["tokens"] += usage_evt.get("prompt_tokens") or 0
        aggregated[model]["requests"] += 1

    return AlbertQuotasResponse(
        limite_tpd=limite_tpd,
        limite_rpd=limite_rpd,
        budget=info.get("budget"),
        modeles=[
            AlbertModelUsage(
                nom=model,
                tokens_aujourd_hui=data["tokens"],
                requetes_aujourd_hui=data["requests"],
            )
            for model, data in sorted(aggregated.items())
        ],
    )
