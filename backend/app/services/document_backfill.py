"""Reconstruction de la table ``documents`` à partir de Qdrant.

Qdrant a longtemps été la seule trace des documents indexés. Ce module rejoue son
contenu dans les tables ``documents`` / ``document_versions``, sans jamais toucher au
disque ni aux points eux-mêmes.

**Qdrant fait foi, pas ``document_uploads``** : un ``doc_id`` présent en base mais
absent de la collection correspond à une ingestion échouée et ne doit pas ressusciter
sous forme de document actif.
"""

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
    """Agrège les points de la collection par ``doc_id``.

    Les points dépourvus de ``doc_id`` sont ignorés : ce sont ceux de ``feedback_job``,
    qui indexent une question et non un document. Les inclure créerait des documents
    fantômes portant le texte d'une réponse.
    """
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
            entree = docs.setdefault(doc_id, {
                "doc_id": doc_id,
                "filename": p.get("source") or "document",
                "domaine": p.get("domaine") or "",
                "description": p.get("description") or "",
                "content_hash": p.get("content_hash") or None,
                "stored_path": p.get("stored_path") or None,
                "uploaded_by": p.get("uploaded_by") or None,
                "version": p.get("version") or 1,
                "nb_chunks": 0,
            })
            entree["nb_chunks"] += 1
            # Le payload d'un document ancien peut être partiel d'un point à l'autre :
            # on retient la première valeur non vide rencontrée.
            for cle in ("stored_path", "content_hash", "uploaded_by", "description"):
                if not entree[cle] and p.get(cle):
                    entree[cle] = p[cle]

        if offset is None:
            break

    return docs


def _resoudre_stored_path(entree: dict) -> str | None:
    """Chemin du fichier d'origine, ou None s'il n'est plus sur le disque.

    Les documents backfillés gardent leur fichier là où il est — à la racine du dossier
    ``{doc_id}``, sans sous-dossier ``v1/``. Le backfill ne déplace rien.
    """
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

    # Repli sur la trace d'upload quand le payload ne porte pas d'auteur (cas nominal
    # pour les documents antérieurs au champ) — l'absence d'auteur reste acceptable.
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
            db.add(Document(
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
            ))
            crees += 1

        if (doc_id, version) not in versions_existantes:
            db.add(DocumentVersion(
                doc_id=doc_id,
                version=version,
                filename=entree["filename"],
                content_hash=entree["content_hash"],
                stored_path=stored_path,
                nb_chunks=entree["nb_chunks"],
                taille_octets=os.path.getsize(stored_path) if stored_path and os.path.isfile(stored_path) else None,
                uploaded_by=auteur,
            ))
            versions_creees += 1

    db.commit()

    return {
        "documents_qdrant": len(docs),
        "documents_crees": crees,
        "documents_existants": len(docs) - crees,
        "versions_creees": versions_creees,
    }
