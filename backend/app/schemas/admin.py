from typing import Any, Literal

from pydantic import BaseModel


class ServiceStatus(BaseModel):
    status: Literal["ok", "error"]
    detail: str | None = None
    latency_ms: int | None = None


class FunctionalStats(BaseModel):
    nb_documents: int = 0
    nb_reponses_validees: int = 0
    tickets_echoues: int = 0
    tickets_bloques: int = 0
    documents_echoues: int = 0
    celery_pending_ingestion: int | None = None
    celery_pending_questions: int | None = None
    celery_workers_ingestion: int | None = None
    celery_workers_questions: int | None = None
    derniere_activite: str | None = None


class HealthResponse(BaseModel):
    postgres: ServiceStatus
    qdrant: ServiceStatus
    valkey: ServiceStatus
    albert_embeddings: ServiceStatus
    albert_llm: ServiceStatus
    albert_reranker: ServiceStatus
    celery_ingestion: ServiceStatus
    celery_questions: ServiceStatus
    stats: FunctionalStats


class DocumentIncident(BaseModel):
    task_id: str
    filename: str | None = None
    domaine: str | None = None
    erreur: str | None = None


class TicketIncident(BaseModel):
    id: str
    question: str
    domaine: str
    statut_job: str
    erreur: str | None = None
    created_at: str


class IncidentsResponse(BaseModel):
    tickets_echoues: list[TicketIncident]
    tickets_bloques: list[TicketIncident]
    documents_echoues: list[DocumentIncident]


class GroupeCreate(BaseModel):
    nom: str
    domaine: str


class ConfigPayload(BaseModel):
    value: Any


class ChefPayload(BaseModel):
    is_chef: bool
