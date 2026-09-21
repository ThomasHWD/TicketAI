"""Reconstructs ``documents`` from Qdrant. Qdrant is authoritative — a doc_id in DB but absent from the collection"""

import os
import uuid

from app.config import settings
from app.models.document import Document
from app.models.document_upload import DocumentUpload
from app.models.document_version import DocumentVersion
from app.services.qdrant import COLLECTION_NAME, client
from sqlalchemy.orm import Session

SCROLL_BATCH = 256


def _uuid_ou_none(valeur) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(valeur))
    except (ValueError, AttributeError, TypeError):
        return None


def collecter_documents_qdrant() -> dict[str, dict]:
    """Aggregate collection points by ``doc_id``; points without ``doc_id`` are response-feedback points and would"""
    docs: dict[str, dict] = {}
    offset = None

    while True:
        points, offset = client.scroll(
            collection_name=COLLECTION_NAME,
            with_payload=True,
            with_vectors=False,
            limit=SCROLL_BATCH,
            offset=offset,
        )
        for point in points:
            p = point.payload or {}
            doc_id = p.get("doc_id")
            if not doc_id:
                continue
            entree = docs.setdefault(
                doc_id,
                {
                    "doc_id": doc_id,
                    "filename": p.get("source") or "document",
                    "domaine": p.get("domaine") or "",
                    "description": p.get("description") or "",
                    "content_hash": p.get("content_hash") or None,
                    "stored_path": p.get("stored_path") or None,
                    "uploaded_by": p.get("uploaded_by") or None,
                    "version": p.get("version") or 1,
                    "nb_chunks": 0,
                },
            )
            entree["nb_chunks"] += 1
            # Older payloads may be partial across points — keep first non-empty value found.
            for cle in ("stored_path", "content_hash", "uploaded_by", "description"):
                if not entree[cle] and p.get(cle):
                    entree[cle] = p[cle]

        if offset is None:
            break

    return docs


def _resoudre_stored_path(entree: dict) -> str | None:
    """File path, or None if not on disk. Backfilled docs live at root ``{doc_id}/``, no ``v1/`` subdirectory."""
    chemin = entree.get("stored_path")
    if chemin and os.path.isfile(chemin):
        return chemin
    fallback = os.path.join(settings.documents_storage_path, entree["doc_id"], entree["filename"])
    if os.path.isfile(fallback):
        return fallback
    return chemin or None


def reconcilier_documents(db: Session) -> dict:
    """Crée les lignes manquantes. Idempotent : rejouable sans effet de bord."""
    docs = collecter_documents_qdrant()

    existants = {d.doc_id for d in db.query(Document.doc_id).all()}
    versions_existantes = {
        (v.doc_id, v.version) for v in db.query(DocumentVersion.doc_id, DocumentVersion.version).all()
    }

    # Payload may lack author for documents older than the field — fall back to upload trace.
    auteurs: dict[str, uuid.UUID] = {}
    for du in db.query(DocumentUpload.doc_id, DocumentUpload.user_id).all():
        if du.user_id and du.doc_id not in auteurs:
            auteurs[du.doc_id] = du.user_id

    crees = versions_creees = 0

    for doc_id, entree in docs.items():
        stored_path = _resoudre_stored_path(entree)
        auteur = _uuid_ou_none(entree["uploaded_by"]) or auteurs.get(doc_id)
        version = int(entree["version"])

        if doc_id not in existants:
            db.add(
                Document(
                    doc_id=doc_id,
                    version=version,
                    filename=entree["filename"],
                    domaine=entree["domaine"],
                    description=entree["description"],
                    content_hash=entree["content_hash"],
                    stored_path=stored_path,
                    nb_chunks=entree["nb_chunks"],
                    statut="ACTIF",
                    uploaded_by=auteur,
                )
            )
            crees += 1

        if (doc_id, version) not in versions_existantes:
            db.add(
                DocumentVersion(
                    doc_id=doc_id,
                    version=version,
                    filename=entree["filename"],
                    content_hash=entree["content_hash"],
                    stored_path=stored_path,
                    nb_chunks=entree["nb_chunks"],
                    taille_octets=os.path.getsize(stored_path) if stored_path and os.path.isfile(stored_path) else None,
                    uploaded_by=auteur,
                )
            )
            versions_creees += 1

    db.commit()

    return {
        "documents_qdrant": len(docs),
        "documents_crees": crees,
        "documents_existants": len(docs) - crees,
        "versions_creees": versions_creees,
    }
