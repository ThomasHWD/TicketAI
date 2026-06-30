import uuid
from typing import Annotated

from celery.result import AsyncResult
from fastapi import APIRouter, File, HTTPException, UploadFile

from app.workers.celery_app import celery_app
from app.workers.ingestion import ingestion_job

router = APIRouter()

ALLOWED_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/plain",
    "text/markdown",
}

MAX_SIZE_MB = 50


@router.post("/documents")
async def upload_document(domaine: str, file: Annotated[UploadFile, File(...)]):
    # Validation type
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(400, f"Type non supporté : {file.content_type}")

    # Validation taille
    contents = await file.read()
    size_mb = len(contents) / (1024 * 1024)
    if size_mb > MAX_SIZE_MB:
        raise HTTPException(
            400, f"Fichier trop volumineux : {size_mb:.1f} Mo (max {MAX_SIZE_MB} Mo)"
        )

    # Stockage fichier brut
    file_id = str(uuid.uuid4())
    file_path = f"/tmp/ticketai/{file_id}_{file.filename}"

    import os

    os.makedirs("/tmp/ticketai", exist_ok=True)
    with open(file_path, "wb") as f:
        f.write(contents)

    # Push job Celery
    job = ingestion_job.apply_async(
        args=[file_path, file.filename, domaine], queue="queue_ingestion"
    )

    return {"job_id": job.id, "filename": file.filename, "statut": "EN_ATTENTE"}


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
