"""Gestion des utilisateurs et des groupes — réservé aux administrateurs."""

import uuid as _uuid
from typing import Annotated, Any, Literal
from uuid import UUID

import redis as redis_lib
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.core.security import AdminUser
from app.database import SessionLocal
from app.models.groupe import Groupe, user_groups
from app.models.site_config import SiteConfig
from app.models.user import User

router = APIRouter(prefix="/admin", tags=["admin"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _entry_value(entry, name: str) -> str | None:
    """Valeur d'un attribut d'une entrée LDAP, ou None si absent/vide."""
    return str(entry[name].value) if name in entry and entry[name].value else None


DB = Annotated[Session, Depends(get_db)]


# ── Schémas ──────────────────────────────────────────────────────────


class ServiceStatus(BaseModel):
    status: Literal["ok", "error"]
    detail: str | None = None



class FunctionalStats(BaseModel):
    nb_documents: int = 0
    nb_reponses_validees: int = 0
    tickets_echoues: int = 0
    tickets_bloques: int = 0
    documents_echoues: int = 0
    celery_pending_ingestion: int | None = None
    celery_pending_questions: int | None = None
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


# ── Sérialisation ────────────────────────────────────────────────────


def _serialize_groupe(g: Groupe, include_membres: bool = False, db_session=None) -> dict:
    data = {
        "id": str(g.id),
        "nom": g.nom,
        "domaine": g.domaine,
        "created_at": g.created_at.isoformat() if g.created_at else None,
        "nb_membres": len(g.membres),
    }
    if include_membres:
        chef_ids = (
            {
                row.user_id
                for row in db_session.execute(
                    user_groups.select().where(
                        user_groups.c.groupe_id == g.id,
                        user_groups.c.is_chef.is_(True),
                    )
                )
            }
            if db_session
            else set()
        )
        data["membres"] = [{**_serialize_user_summary(u), "is_chef": u.id in chef_ids} for u in g.membres]
    return data


def _serialize_user_summary(u: User) -> dict:
    return {
        "id": str(u.id),
        "email": u.email,
        "prenom": u.prenom,
        "nom": u.nom,
        "role": u.role,
        "departement": u.departement,
        "is_gestionnaire": u.is_gestionnaire,
        "groupes": [{"id": str(g.id), "nom": g.nom, "domaine": g.domaine} for g in u.groupes],
    }


# ── Gestionnaires / utilisateurs ─────────────────────────────────────


@router.get("/gestionnaires")
def list_gestionnaires(_: AdminUser, db: DB):
    """Liste les membres du groupe gestionnaire depuis l'AD (avec fallback base)."""
    from ldap3 import Connection

    from app.config import settings
    from app.services.ldap_auth import _make_server

    if settings.auth_mode == "ldap":
        try:
            server = _make_server(settings.ldap_server_url)
            svc = Connection(
                server,
                user=settings.ldap_bind_dn,
                password=settings.ldap_bind_password,
                auto_bind=True,
                receive_timeout=settings.ldap_timeout,
            )
            # Récupère le DN exact du groupe
            svc.search(settings.ldap_user_search_base, f"(cn={settings.ldap_group_gestionnaire})", attributes=["cn"])
            if not svc.entries:
                svc.unbind()
                return []
            group_dn = svc.entries[0].entry_dn

            # Recherche récursive (LDAP_MATCHING_RULE_IN_CHAIN) pour inclure les sous-groupes
            svc.search(
                settings.ldap_user_search_base,
                f"(memberOf:1.2.840.113556.1.4.1941:={group_dn})",
                attributes=[
                    settings.ldap_attr_email,
                    settings.ldap_attr_firstname,
                    settings.ldap_attr_lastname,
                    settings.ldap_attr_department,
                ],
            )

            result = []
            emails_vus: set[str] = set()
            for e in svc.entries:
                email = _entry_value(e, settings.ldap_attr_email)
                if not email or email in emails_vus:
                    continue
                emails_vus.add(email)
                db_user = db.query(User).filter(User.email == email).first()
                result.append(
                    {
                        "id": str(db_user.id) if db_user else None,
                        "email": email,
                        "prenom": _entry_value(e, settings.ldap_attr_firstname),
                        "nom": _entry_value(e, settings.ldap_attr_lastname),
                        "departement": _entry_value(e, settings.ldap_attr_department),
                        "is_gestionnaire": True,
                        "role": db_user.role if db_user else "USER",
                    }
                )
            svc.unbind()
            return sorted(result, key=lambda u: (u["nom"] or "", u["prenom"] or ""))
        except Exception:
            pass  # fallback base si l'AD est injoignable

    # Fallback : base de données
    users = db.query(User).filter(User.is_gestionnaire.is_(True)).order_by(User.nom, User.prenom).all()
    return [_serialize_user_summary(u) for u in users]


# ── Groupes ──────────────────────────────────────────────────────────


@router.get("/groupes")
def list_groupes(_: AdminUser, db: DB):
    """Liste tous les groupes avec leur nombre de membres."""
    groupes = db.query(Groupe).order_by(Groupe.domaine, Groupe.nom).all()
    return [_serialize_groupe(g, include_membres=True, db_session=db) for g in groupes]


@router.get("/domaines")
def list_domaines(_: AdminUser, db: DB):
    """Liste les domaines existants (valeurs distinctes sur les groupes)."""
    rows = db.query(Groupe.domaine).distinct().order_by(Groupe.domaine).all()
    return [r[0] for r in rows]


@router.post("/groupes", status_code=status.HTTP_201_CREATED)
def create_groupe(body: GroupeCreate, _: AdminUser, db: DB):
    """Crée un groupe."""
    domaine = body.domaine.strip().upper()
    if not domaine:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Le domaine est obligatoire.")
    groupe = Groupe(nom=body.nom, domaine=domaine)
    db.add(groupe)
    try:
        db.commit()
    except IntegrityError as err:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Un groupe existe déjà pour le domaine {domaine}.",
        ) from err
    db.refresh(groupe)
    return _serialize_groupe(groupe, include_membres=True, db_session=db)


@router.delete("/groupes/{groupe_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_groupe(groupe_id: UUID, _: AdminUser, db: DB):
    """Supprime un groupe et ses associations membres."""
    groupe = db.query(Groupe).filter(Groupe.id == groupe_id).first()
    if groupe is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Groupe introuvable.")
    db.delete(groupe)
    db.commit()


# ── Membres ──────────────────────────────────────────────────────────


@router.post("/groupes/{groupe_id}/membres/{user_id}", status_code=status.HTTP_201_CREATED)
def add_membre(groupe_id: UUID, user_id: str, _: AdminUser, db: DB):
    """Ajoute un utilisateur dans un groupe. user_id peut être un UUID ou un email (provisionnement JIT)."""
    groupe = db.query(Groupe).filter(Groupe.id == groupe_id).first()
    if groupe is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Groupe introuvable.")

    # Résolution de l'utilisateur : UUID en base ou email (provisionnement depuis l'AD)
    user = None
    if "@" in user_id:
        user = db.query(User).filter(User.email == user_id).first()
        if user is None:
            # Provisionnement JIT depuis l'AD
            from ldap3 import Connection

            from app.config import settings
            from app.services.ldap_auth import _make_server, _search_attributes

            try:
                server = _make_server(settings.ldap_server_url)
                svc = Connection(
                    server,
                    user=settings.ldap_bind_dn,
                    password=settings.ldap_bind_password,
                    auto_bind=True,
                    receive_timeout=settings.ldap_timeout,
                )
                svc.search(
                    settings.ldap_user_search_base,
                    f"({settings.ldap_attr_email}={user_id})",
                    attributes=_search_attributes(),
                )
                if svc.entries:
                    e = svc.entries[0]
                    user = User(
                        email=user_id,
                        prenom=_entry_value(e, settings.ldap_attr_firstname),
                        nom=_entry_value(e, settings.ldap_attr_lastname),
                        departement=_entry_value(e, settings.ldap_attr_department),
                        is_gestionnaire=True,
                        role="USER",
                    )
                    db.add(user)
                    db.flush()
                svc.unbind()
            except Exception:
                pass
    else:
        try:
            user = db.query(User).filter(User.id == UUID(user_id)).first()
        except ValueError:
            pass

    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Utilisateur introuvable.")
    if user not in groupe.membres:
        groupe.membres.append(user)
        db.commit()
    db.refresh(groupe)
    return _serialize_groupe(groupe, include_membres=True, db_session=db)


@router.delete("/groupes/{groupe_id}/membres/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_membre(groupe_id: UUID, user_id: UUID, _: AdminUser, db: DB):
    """Retire un utilisateur d'un groupe."""
    groupe = db.query(Groupe).filter(Groupe.id == groupe_id).first()
    if groupe is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Groupe introuvable.")
    user = db.query(User).filter(User.id == user_id).first()
    if user and user in groupe.membres:
        groupe.membres.remove(user)
        db.commit()


# ── Santé des services ───────────────────────────────────────────────


@router.get("/health", response_model=HealthResponse)
def get_health(_: AdminUser, db: DB) -> HealthResponse:
    from sqlalchemy import text

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

    import httpx
    albert_auth = {"Authorization": f"Bearer {settings.albert_api_key}"}

    def _ping_albert(url: str) -> ServiceStatus:
        try:
            httpx.get(url, headers=albert_auth, timeout=3.0)
            return ServiceStatus(status="ok")
        except Exception as e:
            return ServiceStatus(status="error", detail=str(e))

    al_emb = _ping_albert(settings.albert_embeddings_url)
    al_llm = _ping_albert(settings.albert_llm_url)
    al_rer = _ping_albert(settings.albert_reranker_url)

    def _celery_queue_status(queue: str) -> ServiceStatus:
        try:
            from app.workers.celery_app import celery_app
            inspector = celery_app.control.inspect(timeout=2)
            queues = inspector.active_queues() or {}
            active = any(
                any(q.get("name") == queue for q in worker_queues)
                for worker_queues in queues.values()
            )
            if active:
                return ServiceStatus(status="ok")
            return ServiceStatus(status="error", detail="Aucun worker actif sur cette queue")
        except Exception as e:
            return ServiceStatus(status="error", detail=str(e))

    cel_ing = _celery_queue_status("queue_ingestion")
    cel_q   = _celery_queue_status("queue_questions")

    # ── Stats fonctionnelles ─────────────────────────────────────────
    from datetime import datetime, timedelta, timezone
    from sqlalchemy import distinct
    from app.models.ticket import Ticket
    from app.models.reponse import Reponse
    from app.models.reponse_chunk import ReponseChunk

    # Nombre de documents (doc_id distincts dans reponse_chunks)
    nb_documents = db.query(distinct(ReponseChunk.doc_id)).count()

    # Nombre de réponses validées
    nb_reponses_validees = db.query(Reponse).filter(Reponse.statut == "VALIDÉE").count()

    # Tickets échoués
    tickets_echoues = db.query(Ticket).filter(Ticket.statut_job == "ÉCHOUÉ").count()

    # Tickets bloqués (EN_COURS > 10 min)
    seuil = datetime.now(timezone.utc) - timedelta(minutes=10)
    tickets_bloques = (
        db.query(Ticket)
        .filter(Ticket.statut_job == "EN_COURS", Ticket.created_at < seuil)
        .count()
    )

    # Longueur des files Celery + documents échoués via Redis
    celery_pending_ingestion: int | None = None
    celery_pending_questions: int | None = None
    documents_echoues = 0
    try:
        import json as _json
        r = redis_lib.from_url(settings.valkey_url, socket_connect_timeout=2)
        celery_pending_ingestion = r.llen("queue_ingestion")
        celery_pending_questions = r.llen("queue_questions")
        # Parcourir les résultats Celery pour compter les ingestions échouées
        for key in r.scan_iter("celery-task-meta-*", count=200):
            raw = r.get(key)
            if raw:
                try:
                    meta = _json.loads(raw)
                    if (
                        meta.get("status") == "FAILURE"
                        and "ingestion_job" in str(meta.get("task_name") or meta.get("name") or "")
                    ):
                        documents_echoues += 1
                except Exception:
                    pass
    except Exception:
        pass

    # Dernière activité (ticket traité le plus récent)
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
        stats=FunctionalStats(
            nb_documents=nb_documents,
            nb_reponses_validees=nb_reponses_validees,
            tickets_echoues=tickets_echoues,
            tickets_bloques=tickets_bloques,
            documents_echoues=documents_echoues,
            celery_pending_ingestion=celery_pending_ingestion,
            celery_pending_questions=celery_pending_questions,
            derniere_activite=derniere_activite,
        ),
    )


# ── Incidents ────────────────────────────────────────────────────────


def _scan_document_incidents() -> list[DocumentIncident]:
    """Parcourt les résultats Celery dans Redis pour trouver les ingestions échouées."""
    import json as _json
    incidents: list[DocumentIncident] = []
    try:
        r = redis_lib.from_url(settings.valkey_url, socket_connect_timeout=2)
        for key in r.scan_iter("celery-task-meta-*", count=500):
            raw = r.get(key)
            if not raw:
                continue
            try:
                meta = _json.loads(raw)
                if meta.get("status") != "FAILURE":
                    continue
                task_name = meta.get("task_name") or meta.get("name") or ""
                if "ingestion_job" not in str(task_name):
                    continue
                kwargs = meta.get("kwargs") or {}
                erreur = None
                result = meta.get("result")
                if isinstance(result, dict):
                    raw_err = result.get("exc_message") or str(result)
                    erreur = raw_err[0] if isinstance(raw_err, list) else str(raw_err)
                elif result:
                    erreur = str(result)
                task_id = key.decode() if isinstance(key, bytes) else str(key)
                task_id = task_id.replace("celery-task-meta-", "")
                incidents.append(DocumentIncident(
                    task_id=task_id,
                    filename=kwargs.get("filename"),
                    domaine=kwargs.get("domaine"),
                    erreur=erreur,
                ))
            except Exception:
                pass
    except Exception:
        pass
    return incidents


@router.get("/incidents", response_model=IncidentsResponse)
def get_incidents(_: AdminUser, db: DB) -> IncidentsResponse:
    from datetime import datetime, timedelta, timezone
    from app.models.ticket import Ticket

    echoues = (
        db.query(Ticket)
        .filter(Ticket.statut_job == "ÉCHOUÉ")
        .order_by(Ticket.created_at.desc())
        .limit(50)
        .all()
    )

    seuil = datetime.now(timezone.utc) - timedelta(minutes=10)
    bloques = (
        db.query(Ticket)
        .filter(Ticket.statut_job == "EN_COURS", Ticket.created_at < seuil)
        .order_by(Ticket.created_at.desc())
        .limit(50)
        .all()
    )

    def _serialize_ticket(t: Ticket) -> TicketIncident:
        return TicketIncident(
            id=str(t.id),
            question=t.question,
            domaine=t.domaine,
            statut_job=t.statut_job,
            erreur=t.erreur,
            created_at=t.created_at.isoformat() if t.created_at else "",
        )

    return IncidentsResponse(
        tickets_echoues=[_serialize_ticket(t) for t in echoues],
        tickets_bloques=[_serialize_ticket(t) for t in bloques],
        documents_echoues=_scan_document_incidents(),
    )


@router.delete("/tickets/{ticket_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_ticket_incident(ticket_id: UUID, _: AdminUser, db: DB):
    from app.models.ticket import Ticket

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
    from app.models.ticket import Ticket

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


@router.get("/documents/{task_id}/download")
def download_document(task_id: str, _: AdminUser):
    import json as _json
    import os

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
    import json as _json
    import os

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
    import os

    try:
        r = redis_lib.from_url(settings.valkey_url, socket_connect_timeout=2)
        raw = r.get(f"celery-task-meta-{task_id}")
        if not raw:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tâche introuvable.")
        import json as _json
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


# ── Configuration du site ────────────────────────────────────────────

# Valeurs par défaut pour chaque clé de config
_CONFIG_DEFAULTS: dict[str, Any] = {
    "banner": {"active": False, "message": "", "url": ""},
}


class ConfigPayload(BaseModel):
    value: Any


@router.get("/config")
def get_config(db: DB):
    """Retourne toute la configuration du site (accessible à tout utilisateur authentifié)."""
    rows = db.query(SiteConfig).all()
    result = dict(_CONFIG_DEFAULTS)
    for row in rows:
        result[row.key] = row.value
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
    return {"key": row.key, "value": row.value}


class ChefPayload(BaseModel):
    is_chef: bool


@router.put("/groupes/{groupe_id}/membres/{user_id}/chef")
def set_chef(groupe_id: UUID, user_id: UUID, body: ChefPayload, _: AdminUser, db: DB):
    """Désigne ou retire le rôle de chef pour un membre d'un groupe."""
    groupe = db.query(Groupe).filter(Groupe.id == groupe_id).first()
    if groupe is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Groupe introuvable.")
    user = db.query(User).filter(User.id == user_id).first()
    if user is None or user not in groupe.membres:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Membre introuvable dans ce groupe.")
    db.execute(
        user_groups.update()
        .where(user_groups.c.groupe_id == groupe_id, user_groups.c.user_id == user_id)
        .values(is_chef=body.is_chef)
    )
    db.commit()
    db.refresh(groupe)
    return _serialize_groupe(groupe, include_membres=True, db_session=db)
