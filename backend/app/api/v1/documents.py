import hashlib
import os
import re
import shutil
import uuid
from typing import Annotated

from celery.result import AsyncResult
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from qdrant_client.models import FieldCondition, Filter, FilterSelector, MatchValue
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.core.permissions import check_domain_read, check_domain_write, user_domaines
from app.core.security import AdminUser, BackofficeUser, CurrentUser
from app.database import SessionLocal
from app.models.document import Document
from app.models.document_version import DocumentVersion
from app.models.groupe import Groupe
from app.services.obsolescence import RAISON_SUPPRESSION, marquer_obsoletes
from app.services.qdrant import COLLECTION_NAME, client
from app.workers.celery_app import celery_app
from app.workers.ingestion import ingestion_job

router = APIRouter()

# Statuts d'un document encore existant — SUPPRIMÉ est un soft-delete, conservé pour
# garder la trace des reponse_chunks qui le citent.
STATUTS_VIVANTS = ("ACTIF", "EN_MAJ")


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


def get_document_vivant(db: Session, doc_id: str) -> Document:
    """Document non supprimé, ou 404."""
    doc = (
        db.query(Document)
        .filter(Document.doc_id == doc_id, Document.statut.in_(STATUTS_VIVANTS))
        .first()
    )
    if doc is None:
        raise HTTPException(404, "Document introuvable")
    return doc


def chemin_du_fichier(doc: Document) -> str | None:
    """Chemin sur disque du fichier courant, ou None s'il a disparu.

    Le repli couvre les documents backfillés, dont le fichier est resté à la racine
    du dossier ``{doc_id}`` au lieu d'un sous-dossier ``v{n}/``.
    """
    if doc.stored_path and os.path.isfile(doc.stored_path):
        return doc.stored_path
    repli = os.path.join(settings.documents_storage_path, doc.doc_id, doc.filename)
    return repli if os.path.isfile(repli) else None


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

    # Détection de doublon via hash SHA-256 du contenu, dans le domaine visé seulement.
    # search_hybrid filtre strictement par domaine : un PDF ingéré en IT est invisible
    # en RH, l'ancien scroll global interdisait pourtant de l'y ingérer.
    content_hash = hashlib.sha256(contents).hexdigest()
    doublon = (
        db.query(Document)
        .filter(
            Document.content_hash == content_hash,
            Document.domaine == domaine,
            Document.statut.in_(STATUTS_VIVANTS),
        )
        .first()
    )
    if doublon:
        return {
            "job_id": None,
            "filename": doublon.filename,
            "doc_id": doublon.doc_id,
            "domaine": doublon.domaine,
            "version": doublon.version,
            "statut": "DÉJÀ_INDEXÉ",
        }

    # Stockage fichier brut (seulement si document nouveau)
    file_id = str(uuid.uuid4())
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    file_path = os.path.join(UPLOAD_DIR, f"{file_id}_{filename}")
    with open(file_path, "wb") as f:
        f.write(contents)

    # Push job Celery — tout en kwargs : /admin/documents/{task_id}/retry rejoue la
    # tâche depuis `meta["kwargs"]`, les arguments positionnels y sont invisibles.
    # doc_id est fixé ici pour rester stable d'un retry à l'autre.
    doc_id = str(uuid.uuid4())
    job = ingestion_job.apply_async(
        kwargs={
            "file_path": file_path,
            "filename": filename,
            "domaine": domaine,
            "description": description.strip(),
            "content_hash": content_hash,
            "uploaded_by": str(current_user.id),
            "doc_id": doc_id,
        },
        queue="queue_ingestion",
    )

    return {"job_id": job.id, "filename": filename, "doc_id": doc_id, "statut": "EN_ATTENTE"}


@router.get("/documents")
async def list_documents(
    current_user: BackofficeUser,
    db: DB,
    domaine: str | None = None,
    domaines: str | None = None,
):
    """Liste des documents indexés, lue en base.

    Volontairement **non paginée** : la recherche d'``AllDocs`` filtre côté client sur
    la liste complète, paginer la casserait.
    """
    q = db.query(Document).filter(Document.statut.in_(STATUTS_VIVANTS))

    if domaines:
        q = q.filter(Document.domaine.in_([d.strip().upper() for d in domaines.split(",") if d.strip()]))
    elif domaine:
        q = q.filter(Document.domaine == domaine.upper())
    elif current_user.role != "ADMIN":
        # Backoffice sans filtre explicite : limité à ses propres domaines
        allowed = list(user_domaines(current_user))
        if not allowed:
            return {"total": 0, "items": []}
        q = q.filter(Document.domaine.in_(allowed))

    docs = q.order_by(Document.updated_at.desc()).all()

    nb_versions = dict(
        db.query(DocumentVersion.doc_id, func.count())
        .filter(DocumentVersion.doc_id.in_([d.doc_id for d in docs]))
        .group_by(DocumentVersion.doc_id)
        .all()
    ) if docs else {}

    items = [
        {
            "doc_id": d.doc_id,
            "filename": d.filename,
            "domaine": d.domaine,
            "stored_path": d.stored_path,
            "description": d.description,
            "nb_chunks": d.nb_chunks,
            "version": d.version,
            "statut": d.statut,
            "nb_versions": nb_versions.get(d.doc_id, 1),
            "updated_at": d.updated_at.isoformat() if d.updated_at else None,
        }
        for d in docs
    ]
    return {"total": len(items), "items": items}


@router.get("/documents/{doc_id}/chunks")
async def get_document_chunks(doc_id: str, current_user: BackofficeUser, db: DB):
    """Retourne les chunks indexés du document."""
    doc = get_document_vivant(db, doc_id)
    check_domain_read(doc.domaine, current_user)

    results, _ = client.scroll(
        collection_name=COLLECTION_NAME,
        scroll_filter=Filter(must=[FieldCondition(key="doc_id", match=MatchValue(value=doc_id))]),
        with_payload=True,
        with_vectors=False,
        limit=1000,
    )

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
async def download_document(doc_id: str, current_user: BackofficeUser, db: DB):
    """Renvoie le fichier original stocké sur disque."""
    doc = get_document_vivant(db, doc_id)
    check_domain_read(doc.domaine, current_user)

    chemin = chemin_du_fichier(doc)
    if chemin is None:
        raise HTTPException(404, "Fichier non disponible sur disque")

    return FileResponse(
        path=chemin,
        filename=doc.filename,
        media_type="application/octet-stream",
    )


@router.delete("/documents/{doc_id}")
async def delete_document(doc_id: str, current_user: AdminUser, db: DB):
    """Retire un document de l'index et du disque.

    La ligne `documents` est conservée en `SUPPRIMÉ` : les `reponse_chunks` qui la
    citent restent interprétables, et son `content_hash` cesse de bloquer un
    ré-upload du même contenu.
    """
    doc = get_document_vivant(db, doc_id)
    if doc.statut == "EN_MAJ":
        raise HTTPException(409, "Une mise à jour de ce document est en cours.")

    client.delete(
        collection_name=COLLECTION_NAME,
        points_selector=FilterSelector(
            filter=Filter(must=[FieldCondition(key="doc_id", match=MatchValue(value=doc_id))])
        ),
    )

    # Le dossier du document, archives v{n}/ comprises — les fichiers étant rangés par
    # version, effacer le seul dossier de la version courante en laisserait derrière.
    doc_dir = os.path.join(settings.documents_storage_path, doc_id)
    if os.path.isdir(doc_dir):
        shutil.rmtree(doc_dir, ignore_errors=True)

    doc.statut = "SUPPRIMÉ"
    doc.deleted_at = func.now()
    doc.nb_chunks = 0
    db.commit()

    # Tous les chunks ont disparu : chaque réponse fondée sur ce document devient
    # obsolète, sans calcul d'indices.
    obsoletes = marquer_obsoletes(db, doc_id, RAISON_SUPPRESSION, version=doc.version)

    return {"statut": "OK", "doc_id": doc_id, "nb_obsoletes": len(obsoletes)}


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
