import hashlib
import os
import re
import shutil
import uuid
from typing import Annotated

from celery.result import AsyncResult
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from qdrant_client.models import FieldCondition, Filter, FilterSelector, MatchAny, MatchValue
from sqlalchemy.orm import Session

from app.config import settings
from app.core.permissions import check_domain_write, user_domaines
from app.core.security import AdminUser, BackofficeUser, CurrentUser
from app.database import SessionLocal
from app.models.groupe import Groupe
from app.services.qdrant import COLLECTION_NAME, client
from app.workers.celery_app import celery_app
from app.workers.ingestion import ingestion_job

router = APIRouter()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


DB = Annotated[Session, Depends(get_db)]

# Signatures binaires attendues par extension (None = fichier texte → validation UTF-8)
MAGIC_BYTES: dict[str, bytes | None] = {
    ".pdf": b"%PDF",
    ".docx": b"PK\x03\x04",  # DOCX = archive ZIP
    ".txt": None,
    ".md": None,
}

MAX_SIZE_MB = 50

UPLOAD_DIR = os.environ.get("UPLOAD_DIR", "/tmp/ticketai")


def sanitize_filename(filename: str | None) -> str:
    """Neutralise le nom de fichier fourni par le client (path traversal, null bytes)."""
    name = os.path.basename(filename or "").replace("\x00", "")
    name = re.sub(r"[^\w.\- ]", "_", name)
    if not name or name.startswith("."):
        raise HTTPException(400, "Nom de fichier invalide")
    return name


@router.post("/documents")
async def upload_document(
    current_user: BackofficeUser,
    domaine: str,
    file: Annotated[UploadFile, File(...)],
    db: DB,
    description: str = "",
):
    # Validation domaine
    domaine = domaine.upper()
    domaines_valides = {r[0] for r in db.query(Groupe.domaine).distinct().all()}
    if not domaines_valides:
        raise HTTPException(400, "Aucun domaine configuré. Créez d'abord un groupe.")
    if domaine not in domaines_valides:
        raise HTTPException(400, f"Domaine invalide : {domaine}")
    check_domain_write(domaine, current_user)

    # Validation nom + extension (le Content-Type client est déclaratif, donc spoofable)
    filename = sanitize_filename(file.filename)
    ext = os.path.splitext(filename)[1].lower()
    if ext not in MAGIC_BYTES:
        raise HTTPException(400, f"Extension non supportée : {ext}")

    # Validation taille
    contents = await file.read()
    size_mb = len(contents) / (1024 * 1024)
    if size_mb > MAX_SIZE_MB:
        raise HTTPException(400, f"Fichier trop volumineux : {size_mb:.1f} Mo (max {MAX_SIZE_MB} Mo)")

    # Validation du contenu réel via magic bytes
    magic = MAGIC_BYTES[ext]
    if magic is not None:
        if not contents.startswith(magic):
            raise HTTPException(400, f"Contenu du fichier incohérent avec l'extension {ext}")
    else:
        try:
            contents.decode("utf-8")
        except UnicodeDecodeError:
            raise HTTPException(400, "Fichier texte non encodé en UTF-8") from None

    # Détection de doublon via hash SHA-256 du contenu
    content_hash = hashlib.sha256(contents).hexdigest()
    existing, _ = client.scroll(
        collection_name=COLLECTION_NAME,
        scroll_filter=Filter(must=[FieldCondition(key="content_hash", match=MatchValue(value=content_hash))]),
        with_payload=["doc_id", "source"],
        with_vectors=False,
        limit=1,
    )
    if existing:
        p = existing[0].payload or {}
        return {
            "job_id": None,
            "filename": p.get("source", filename),
            "doc_id": p.get("doc_id"),
            "statut": "DÉJÀ_INDEXÉ",
        }

    # Stockage fichier brut (seulement si document nouveau)
    file_id = str(uuid.uuid4())
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    file_path = os.path.join(UPLOAD_DIR, f"{file_id}_{filename}")
    with open(file_path, "wb") as f:
        f.write(contents)

    # Push job Celery
    job = ingestion_job.apply_async(
        args=[file_path, filename, domaine, description.strip(), content_hash],
        kwargs={"uploaded_by": str(current_user.id)},
        queue="queue_ingestion",
    )

    return {"job_id": job.id, "filename": filename, "statut": "EN_ATTENTE"}


@router.get("/documents")
async def list_documents(current_user: BackofficeUser, domaine: str | None = None, domaines: str | None = None):
    """Retourne la liste des documents indexés dans Qdrant, groupés par doc_id."""
    filter_: Filter | None = None
    if domaines:
        domaine_list = [d.strip().upper() for d in domaines.split(",") if d.strip()]
        filter_ = Filter(must=[FieldCondition(key="domaine", match=MatchAny(any=domaine_list))])
    elif domaine:
        domaine = domaine.upper()
        filter_ = Filter(must=[FieldCondition(key="domaine", match=MatchValue(value=domaine))])
    elif current_user.role != "ADMIN":
        # Backoffice sans filtre explicite : limité à ses propres domaines
        allowed = list(user_domaines(current_user))
        if allowed:
            filter_ = Filter(must=[FieldCondition(key="domaine", match=MatchAny(any=allowed))])
        else:
            return {"total": 0, "items": []}

    docs: dict[str, dict] = {}
    offset = None

    while True:
        results, offset = client.scroll(
            collection_name=COLLECTION_NAME,
            scroll_filter=filter_,
            with_payload=True,
            with_vectors=False,
            limit=100,
            offset=offset,
        )
        for point in results:
            p = point.payload or {}
            doc_id = p.get("doc_id")
            if not doc_id:
                continue
            if doc_id not in docs:
                docs[doc_id] = {
                    "doc_id": doc_id,
                    "filename": p.get("source"),
                    "domaine": p.get("domaine"),
                    "stored_path": p.get("stored_path"),
                    "description": p.get("description", ""),
                    "nb_chunks": 0,
                }
            docs[doc_id]["nb_chunks"] += 1

        if offset is None:
            break

    return {"total": len(docs), "items": list(docs.values())}


@router.get("/documents/{doc_id}/chunks")
async def get_document_chunks(doc_id: str, current_user: BackofficeUser):
    """Retourne les chunks d'un document indexé."""
    results, _ = client.scroll(
        collection_name=COLLECTION_NAME,
        scroll_filter=Filter(must=[FieldCondition(key="doc_id", match=MatchValue(value=doc_id))]),
        with_payload=True,
        with_vectors=False,
        limit=1000,
    )
    if not results:
        raise HTTPException(404, "Document introuvable")

    chunks = sorted(
        [
            {"chunk_index": p.payload.get("chunk_index"), "contenu": p.payload.get("contenu")}
            for p in results
            if p.payload
        ],
        key=lambda x: x["chunk_index"] or 0,
    )
    return {"doc_id": doc_id, "chunks": chunks}


@router.get("/documents/{doc_id}/download")
async def download_document(doc_id: str, current_user: BackofficeUser):
    """Renvoie le fichier original stocké sur disque."""
    results, _ = client.scroll(
        collection_name=COLLECTION_NAME,
        scroll_filter=Filter(must=[FieldCondition(key="doc_id", match=MatchValue(value=doc_id))]),
        with_payload=["stored_path", "source"],
        with_vectors=False,
        limit=1,
    )
    if not results:
        raise HTTPException(404, "Document introuvable")

    payload = results[0].payload or {}
    stored_path = payload.get("stored_path")
    filename = payload.get("source") or os.path.basename(stored_path or "")

    # Fallback pour les documents indexés avant la correction du worker
    if (not stored_path or not os.path.isfile(stored_path)) and filename:
        stored_path = os.path.join(settings.documents_storage_path, doc_id, filename)

    if not stored_path or not os.path.isfile(stored_path):
        raise HTTPException(404, "Fichier non disponible sur disque")

    return FileResponse(
        path=stored_path,
        filename=filename,
        media_type="application/octet-stream",
    )


@router.delete("/documents/{doc_id}")
async def delete_document(doc_id: str, current_user: AdminUser):
    """Supprime un document de Qdrant et du stockage permanent."""
    doc_filter = Filter(must=[FieldCondition(key="doc_id", match=MatchValue(value=doc_id))])

    results, _ = client.scroll(
        collection_name=COLLECTION_NAME,
        scroll_filter=doc_filter,
        with_payload=["stored_path"],
        with_vectors=False,
        limit=1,
    )
    if not results:
        raise HTTPException(404, "Document introuvable")

    stored_path = (results[0].payload or {}).get("stored_path")

    client.delete(
        collection_name=COLLECTION_NAME,
        points_selector=FilterSelector(filter=doc_filter),
    )

    if stored_path:
        doc_dir = os.path.dirname(stored_path)
        if os.path.isdir(doc_dir):
            shutil.rmtree(doc_dir, ignore_errors=True)

    return {"statut": "OK", "doc_id": doc_id}


@router.get("/documents/{job_id}/status")
async def statut_document(job_id: str, current_user: CurrentUser):
    result = AsyncResult(job_id, app=celery_app)

    reponse = {
        "job_id": job_id,
        "statut": result.status,  # PENDING / STARTED / SUCCESS / FAILURE / RETRY
    }

    if result.status == "SUCCESS":
        reponse["resultat"] = result.result

    elif result.status == "FAILURE":
        reponse["erreur"] = str(result.result)

    return reponse
