"""Helpers extraits de api/v1/admin.py : sérialisation, incidents, santé des services."""

import json as _json
import time
from typing import Any

import httpx
import redis as redis_lib
from app.config import settings
from app.models.groupe import Groupe, user_groups
from app.models.user import User
from app.schemas.admin import DocumentIncident, ServiceStatus

_CONFIG_DEFAULTS: dict[str, Any] = {
    "banner": {"active": False, "message": "", "url": ""},
    "maintenance": {"active": False, "message": ""},
}


def entry_value(entry, name: str) -> str | None:
    """Valeur d'un attribut d'une entrée LDAP, ou None si absent/vide."""
    return str(entry[name].value) if name in entry and entry[name].value else None


def serialize_user_summary(u: User) -> dict:
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


def serialize_groupe(g: Groupe, include_membres: bool = False, db_session=None) -> dict:
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
        data["membres"] = [{**serialize_user_summary(u), "is_chef": u.id in chef_ids} for u in g.membres]
    return data


def scan_document_incidents() -> list[DocumentIncident]:
    """Parcourt les résultats Celery dans Redis pour trouver les ingestions échouées."""
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
                incidents.append(
                    DocumentIncident(
                        task_id=task_id,
                        filename=kwargs.get("filename"),
                        domaine=kwargs.get("domaine"),
                        erreur=erreur,
                    )
                )
            except Exception:
                pass
    except Exception:
        pass
    return incidents


def ping_albert(url: str, api_key: str) -> ServiceStatus:
    headers = {"Authorization": f"Bearer {api_key}"}
    try:
        t0 = time.perf_counter()
        httpx.get(url, headers=headers, timeout=3.0)
        latency_ms = round((time.perf_counter() - t0) * 1000)
        return ServiceStatus(status="ok", latency_ms=latency_ms)
    except Exception as e:
        return ServiceStatus(status="error", detail=str(e))


def celery_status_and_count(queue: str, celery_queues_info: dict) -> tuple[ServiceStatus, int]:
    workers = [wname for wname, wqueues in celery_queues_info.items() if any(q.get("name") == queue for q in wqueues)]
    if workers:
        return ServiceStatus(status="ok"), len(workers)
    return ServiceStatus(status="error", detail="Aucun worker actif sur cette queue"), 0
