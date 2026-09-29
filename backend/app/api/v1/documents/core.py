import os
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
from app.core.security import BackofficeUser, CurrentUser
from app.database import SessionLocal
from app.models.document import Document
from app.models.document_version import DocumentVersion
from app.models.groupe import Groupe
from app.services.document_service import STATUTS_VIVANTS, UPLOAD_DIR, get_document_vivant, valider_contenu
from app.services.obsolescence import RAISON_SUPPRESSION, marquer_obsoletes, racines, requeuer_en_attente
from app.services.qdrant import COLLECTION_NAME, client
from app.services.retrait import candidats_au_reexamen, passages_du_document, passages_restants
from app.workers.celery_app import celery_app
from app.workers.ingestion import chemin_du_fichier, ingestion_job
from app.workers.retrait import reexamen_retrait_job

router = APIRouter()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


DB = Annotated[Session, Depends(get_db)]


@router.post("/documents")
async def upload_document(
    current_user: BackofficeUser,
    domaine: str,
    file: Annotated[UploadFile, File(...)],
    db: DB,
    description: str = "",
    force_nouveau: bool = False,
):
    domaine = domaine.upper()
    domaines_valides = {r[0] for r in db.query(Groupe.domaine).distinct().all()}
    if not domaines_valides:
        raise HTTPException(400, "Aucun domaine configuré. Créez d'abord un groupe.")
    if domaine not in domaines_valides:
        raise HTTPException(400, f"Domaine invalide : {domaine}")
    check_domain_write(domaine, current_user)

    contents = await file.read()
    filename, content_hash = valider_contenu(file.filename, contents)

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

    homonyme = (
        db.query(Document)
        .filter(
            Document.filename == filename,
            Document.domaine == domaine,
            Document.statut.in_(STATUTS_VIVANTS),
        )
        .first()
    )
    if homonyme and not force_nouveau:
        raise HTTPException(
            409,
            detail={
                "code": "DOCUMENT_HOMONYME",
                "doc_id": homonyme.doc_id,
                "filename": homonyme.filename,
                "domaine": homonyme.domaine,
                "version": homonyme.version,
                "nb_chunks": homonyme.nb_chunks,
            },
        )

    file_id = str(uuid.uuid4())
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    file_path = os.path.join(UPLOAD_DIR, f"{file_id}_{filename}")
    with open(file_path, "wb") as f:
        f.write(contents)

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
    limit: int = 500,
):
    """Liste des documents indexés (filtrage côté client, cap à 500 par défaut)."""
    limit = min(limit, 1000)
    q = db.query(Document).filter(Document.statut.in_(STATUTS_VIVANTS))

    if current_user.role != "ADMIN":
        allowed = user_domaines(current_user)
        if domaines:
            requested = {d.strip().upper() for d in domaines.split(",") if d.strip()}
            allowed = allowed & requested
        elif domaine:
            d = domaine.upper()
            if d not in allowed:
                return {"total": 0, "items": []}
            allowed = {d}
        if not allowed:
            return {"total": 0, "items": []}
        q = q.filter(Document.domaine.in_(allowed))
    elif domaines:
        q = q.filter(Document.domaine.in_([d.strip().upper() for d in domaines.split(",") if d.strip()]))
    elif domaine:
        q = q.filter(Document.domaine == domaine.upper())

    docs = q.order_by(Document.updated_at.desc()).limit(limit).all()

    nb_versions = (
        dict(
            db.query(DocumentVersion.doc_id, func.count())
            .filter(DocumentVersion.doc_id.in_([d.doc_id for d in docs]))
            .group_by(DocumentVersion.doc_id)
            .all()
        )
        if docs
        else {}
    )

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

    chemin = chemin_du_fichier(doc.doc_id, doc.filename, doc.stored_path)
    if chemin is None:
        raise HTTPException(404, "Fichier non disponible sur disque")

    return FileResponse(path=chemin, filename=doc.filename, media_type="application/octet-stream")


@router.delete("/documents/{doc_id}")
async def delete_document(doc_id: str, current_user: BackofficeUser, db: DB):
    """Retire un document de l'index et du disque (soft-delete)."""
    doc = get_document_vivant(db, doc_id)
    check_domain_write(doc.domaine, current_user)
    if doc.statut == "EN_MAJ":
        raise HTTPException(409, "Une mise à jour de ce document est en cours.")

    # Read before the points go: the judge needs the deleted passages, and the withdrawal below clears the review
    # flags that must keep a flagged family out of the re-examination.
    examens = [
        {
            "reponse_id": str(r.id),
            "passages_retires": passages_du_document(db, r, doc_id),
            "passages_restants": passages_restants(db, r, doc_id),
        }
        for r in candidats_au_reexamen(db, doc_id)
    ]

    client.delete(
        collection_name=COLLECTION_NAME,
        points_selector=FilterSelector(
            filter=Filter(must=[FieldCondition(key="doc_id", match=MatchValue(value=doc_id))])
        ),
    )

    doc_dir = os.path.join(settings.documents_storage_path, doc_id)
    if os.path.isdir(doc_dir):
        shutil.rmtree(doc_dir, ignore_errors=True)

    doc.statut = "SUPPRIMÉ"
    doc.deleted_at = func.now()
    doc.nb_chunks = 0
    db.commit()

    obsoletes, en_attente_obsoletes = marquer_obsoletes(db, doc_id, RAISON_SUPPRESSION, version=doc.version)
    requeuer_en_attente(db, en_attente_obsoletes)
    if examens:
        reexamen_retrait_job.apply_async(kwargs={"doc_id": doc_id, "examens": examens}, queue="queue_questions")

    return {
        "statut": "OK",
        "doc_id": doc_id,
        "nb_obsoletes": len(racines(obsoletes)),
        "nb_a_reexaminer": len(examens),
    }


@router.get("/documents/{job_id}/status")
async def statut_document(job_id: str, current_user: CurrentUser):
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
