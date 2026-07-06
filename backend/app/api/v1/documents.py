import os
import re
import uuid
from typing import Annotated

from celery.result import AsyncResult
from fastapi import APIRouter, File, HTTPException, UploadFile

from app.workers.celery_app import celery_app
from app.workers.ingestion import ingestion_job

router = APIRouter()

DOMAINES_VALIDES = {"IT", "RH", "JURIDIQUE"}

# Signatures binaires attendues par extension (None = fichier texte → validation UTF-8)
MAGIC_BYTES: dict[str, bytes | None] = {
    ".pdf": b"%PDF",
    ".docx": b"PK\x03\x04",  # DOCX = archive ZIP
    ".txt": None,
    ".md": None,
}

MAX_SIZE_MB = 50

UPLOAD_DIR = "/tmp/ticketai"


def sanitize_filename(filename: str | None) -> str:
    """Neutralise le nom de fichier fourni par le client (path traversal, null bytes)."""
    name = os.path.basename(filename or "").replace("\x00", "")
    name = re.sub(r"[^\w.\- ]", "_", name)
    if not name or name.startswith("."):
        raise HTTPException(400, "Nom de fichier invalide")
    return name


@router.post("/documents")
async def upload_document(domaine: str, file: Annotated[UploadFile, File(...)]):
    # Validation domaine
    domaine = domaine.upper()
    if domaine not in DOMAINES_VALIDES:
        raise HTTPException(400, f"Domaine invalide : {domaine}")

    # Validation nom + extension (le Content-Type client est déclaratif, donc spoofable)
    filename = sanitize_filename(file.filename)
    ext = os.path.splitext(filename)[1].lower()
    if ext not in MAGIC_BYTES:
        raise HTTPException(400, f"Extension non supportée : {ext}")

    # Validation taille
    contents = await file.read()
    size_mb = len(contents) / (1024 * 1024)
    if size_mb > MAX_SIZE_MB:
        raise HTTPException(
            400, f"Fichier trop volumineux : {size_mb:.1f} Mo (max {MAX_SIZE_MB} Mo)"
        )

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

    # Stockage fichier brut
    file_id = str(uuid.uuid4())
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    file_path = os.path.join(UPLOAD_DIR, f"{file_id}_{filename}")
    with open(file_path, "wb") as f:
        f.write(contents)

    # Push job Celery
    job = ingestion_job.apply_async(
        args=[file_path, filename, domaine], queue="queue_ingestion"
    )

    return {"job_id": job.id, "filename": filename, "statut": "EN_ATTENTE"}


@router.get("/documents/{job_id}/status")
async def statut_document(job_id: str):
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
