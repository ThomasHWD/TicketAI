import hashlib
import os
import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.permissions import check_domain_read
from app.core.security import BackofficeUser
from app.database import SessionLocal
from app.models.document import Document
from app.models.document_staging import DocumentStaging
from app.models.document_version import DocumentVersion
from app.models.user import User
from app.schemas.document import ConfirmerMajRequest
from app.services.document_service import (
    chemin_de_version,
    get_document_vivant,
    get_version,
    preparer_maj,
    prochaine_version,
    stager_et_analyser,
    valider_contenu,
)
from app.workers.document_update import document_update_job

router = APIRouter()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


DB = Annotated[Session, Depends(get_db)]


@router.post("/documents/{doc_id}/versions/preview")
def previsualiser_maj(
    doc_id: str,
    current_user: BackofficeUser,
    file: Annotated[UploadFile, File(...)],
    db: DB,
    description: str | None = None,
):
    """Analyse impact without modifying anything. ``def`` not ``async def`` — PyMuPDF text extraction is blocking"""
    doc = preparer_maj(db, doc_id, current_user)

    contents = file.file.read()
    filename, content_hash = valider_contenu(file.filename, contents)

    if doc.content_hash is None:
        doc.content_hash = content_hash
        db.commit()
    elif doc.content_hash == content_hash:
        raise HTTPException(409, f"Ce fichier est identique à la version actuelle (v{doc.version}).")

    autre = (
        db.query(Document)
        .filter(
            Document.content_hash == content_hash,
            Document.domaine == doc.domaine,
            Document.doc_id != doc_id,
            Document.statut != "SUPPRIMÉ",
        )
        .first()
    )
    if autre:
        raise HTTPException(409, f"Ce contenu est déjà indexé sous « {autre.filename} » ({doc.domaine}).")

    return stager_et_analyser(
        db,
        doc,
        contents=contents,
        filename=filename,
        content_hash=content_hash,
        description=description if description is not None else doc.description,
        user_id=current_user.id,
    )


@router.post("/documents/{doc_id}/versions/confirm")
async def confirmer_maj(
    doc_id: str,
    payload: ConfirmerMajRequest,
    current_user: BackofficeUser,
    db: DB,
):
    """Réserve le numéro de version, pose le verrou, lance le job."""
    doc = preparer_maj(db, doc_id, current_user)

    try:
        staging_uuid = uuid.UUID(payload.staging_id)
    except ValueError:
        raise HTTPException(404, "Aperçu introuvable") from None

    staging = db.query(DocumentStaging).filter(DocumentStaging.id == staging_uuid).first()
    if staging is None or staging.doc_id != doc_id:
        raise HTTPException(404, "Aperçu introuvable")
    if staging.user_id != current_user.id:
        raise HTTPException(403, "Cet aperçu appartient à un autre utilisateur.")
    expire = staging.expires_at
    if expire.tzinfo is None:
        expire = expire.replace(tzinfo=timezone.utc)
    if expire < datetime.now(timezone.utc):
        raise HTTPException(409, "Cet aperçu a expiré, veuillez redéposer le fichier.")
    if not os.path.isfile(staging.stored_path):
        raise HTTPException(409, "Le fichier analysé n'est plus disponible, veuillez le redéposer.")

    filename = staging.filename
    version_cible = prochaine_version(db, doc)
    doc.statut = "EN_MAJ"
    doc.update_started_at = datetime.now(timezone.utc)
    db.commit()

    job = document_update_job.apply_async(
        kwargs={
            "doc_id": doc_id,
            "new_version": version_cible,
            "file_path": staging.stored_path,
            "filename": staging.filename,
            "description": staging.description,
            "content_hash": staging.content_hash or "",
            "uploaded_by": str(current_user.id),
            "restauree_depuis": staging.restauree_depuis,
        },
        queue="queue_ingestion",
    )

    doc.update_job_id = job.id
    db.delete(staging)
    db.commit()

    return {
        "job_id": job.id,
        "doc_id": doc_id,
        "filename": filename,
        "version": version_cible,
        "statut": "EN_ATTENTE",
    }


@router.get("/documents/{doc_id}/versions")
async def lister_versions(doc_id: str, current_user: BackofficeUser, db: DB):
    """Historique complet, la plus récente en tête."""
    doc = get_document_vivant(db, doc_id)
    check_domain_read(doc.domaine, current_user)

    versions = (
        db.query(DocumentVersion)
        .filter(DocumentVersion.doc_id == doc_id)
        .order_by(DocumentVersion.version.desc())
        .all()
    )

    auteurs = (
        {
            u.id: (f"{u.prenom or ''} {u.nom or ''}".strip() or u.email)
            for u in db.query(User).filter(User.id.in_([v.uploaded_by for v in versions if v.uploaded_by])).all()
        }
        if versions
        else {}
    )

    return {
        "doc_id": doc_id,
        "version_courante": doc.version,
        "items": [
            {
                "version": v.version,
                "filename": v.filename,
                "taille_octets": v.taille_octets,
                "nb_chunks": v.nb_chunks,
                "restauree_depuis": v.restauree_depuis,
                "courante": v.version == doc.version,
                "auteur": auteurs.get(v.uploaded_by),
                "fichier_disponible": chemin_de_version(doc, v) is not None,
                "created_at": v.created_at.isoformat() if v.created_at else None,
                "remplacee_at": v.remplacee_at.isoformat() if v.remplacee_at else None,
            }
            for v in versions
        ],
    }


@router.get("/documents/{doc_id}/versions/{version}/download")
async def telecharger_version(doc_id: str, version: int, current_user: BackofficeUser, db: DB):
    doc = get_document_vivant(db, doc_id)
    check_domain_read(doc.domaine, current_user)
    v = get_version(db, doc, version)

    chemin = chemin_de_version(doc, v)
    if chemin is None:
        raise HTTPException(404, "Fichier non disponible sur disque")

    return FileResponse(path=chemin, filename=v.filename, media_type="application/octet-stream")


@router.post("/documents/{doc_id}/versions/{version}/restaurer")
def restaurer_version(doc_id: str, version: int, current_user: BackofficeUser, db: DB):
    """Impact preview for a version restore — confirmation goes through ``confirm``. ``def`` not ``async def``"""
    doc = preparer_maj(db, doc_id, current_user)
    v = get_version(db, doc, version)

    if v.version == doc.version:
        raise HTTPException(409, f"La v{version} est déjà la version actuelle.")
    if v.content_hash and doc.content_hash and v.content_hash == doc.content_hash:
        raise HTTPException(409, f"La v{version} a le même contenu que la version actuelle (v{doc.version}).")

    chemin = chemin_de_version(doc, v)
    if chemin is None:
        raise HTTPException(409, f"Le fichier archivé de la v{version} n'est plus disponible.")

    with open(chemin, "rb") as f:
        contents = f.read()

    return stager_et_analyser(
        db,
        doc,
        contents=contents,
        filename=v.filename,
        content_hash=v.content_hash or hashlib.sha256(contents).hexdigest(),
        description=doc.description,
        user_id=current_user.id,
        restauree_depuis=version,
    )
