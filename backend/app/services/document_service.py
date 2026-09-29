"""Helpers extraits de api/v1/documents.py : validation, staging, analyse d'impact."""

import hashlib
import os
import re
import uuid
from datetime import datetime, timedelta, timezone

from app.config import settings
from app.core.permissions import check_domain_write
from app.models.document import Document
from app.models.document_staging import DocumentStaging
from app.models.document_version import DocumentVersion
from app.models.reponse import Reponse
from app.models.reponse_chunk import ReponseChunk
from app.services.document_impact import item_impact, items_a_analyser
from app.services.obsolescence import (
    MAX_EXTRAITS,  # noqa: F401 — ré-exporté pour les appelants existants
    analyser_changements,
    extrait,
    indices_modifies,
    racines,
    reponses_obsoletes,
)
from app.services.qdrant import capturer_chunks
from app.services.text_processing import extract_text, texte_complet
from app.workers.ingestion import chemin_du_fichier
from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

STATUTS_VIVANTS = ("ACTIF", "EN_MAJ")

MAGIC_BYTES: dict[str, bytes | None] = {
    ".pdf": b"%PDF",
    ".docx": b"PK\x03\x04",
    ".txt": None,
    ".md": None,
}

MAX_SIZE_MB = 50

UPLOAD_DIR = os.environ.get("UPLOAD_DIR", "/tmp/ticketai")
STAGING_DIR = os.path.join(UPLOAD_DIR, "staging")
STAGING_TTL = timedelta(hours=1)
MAJ_PERIMEE_APRES = timedelta(minutes=30)
MAX_A_RELIRE = 10
MAX_UNITES_AFFICHEES = 5

MUET = {
    "diff_analysable": False,
    "nb_unites": 0,
    "unites": [],
    "nb_ajoutes": 0,
    "extraits_ajoutes": [],
    "nb_retires": 0,
    "extraits_retires": [],
}


def sanitize_filename(filename: str | None) -> str:
    """Neutralise le nom de fichier fourni par le client (path traversal, null bytes)."""
    name = os.path.basename(filename or "").replace("\x00", "")
    name = re.sub(r"[^\w.\- ]", "_", name)
    if not name or name.startswith("."):
        raise HTTPException(400, "Nom de fichier invalide")
    return name


def valider_contenu(filename: str | None, contents: bytes) -> tuple[str, str]:
    """Valide un fichier téléversé et renvoie ``(nom assaini, content_hash)``."""
    filename = sanitize_filename(filename)
    ext = os.path.splitext(filename)[1].lower()
    if ext not in MAGIC_BYTES:
        raise HTTPException(400, f"Extension non supportée : {ext}")

    size_mb = len(contents) / (1024 * 1024)
    if size_mb > MAX_SIZE_MB:
        raise HTTPException(400, f"Fichier trop volumineux : {size_mb:.1f} Mo (max {MAX_SIZE_MB} Mo)")

    magic = MAGIC_BYTES[ext]
    if magic is not None:
        if not contents.startswith(magic):
            raise HTTPException(400, f"Contenu du fichier incohérent avec l'extension {ext}")
    else:
        try:
            contents.decode("utf-8")
        except UnicodeDecodeError:
            raise HTTPException(400, "Fichier texte non encodé en UTF-8") from None

    return filename, hashlib.sha256(contents).hexdigest()


def get_document_vivant(db: Session, doc_id: str) -> Document:
    """Document non supprimé, ou 404."""
    doc = db.query(Document).filter(Document.doc_id == doc_id, Document.statut.in_(STATUTS_VIVANTS)).first()
    if doc is None:
        raise HTTPException(404, "Document introuvable")
    return doc


def maj_en_cours(doc: Document) -> bool:
    """`EN_MAJ` encore crédible — au-delà du délai, le verrou est réputé abandonné."""
    if doc.statut != "EN_MAJ":
        return False
    debut = doc.update_started_at
    if debut is None:
        return True
    if debut.tzinfo is None:
        debut = debut.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - debut < MAJ_PERIMEE_APRES


def purger_staging(db: Session) -> None:
    """Supprime les aperçus expirés, fichier compris."""
    expires = db.query(DocumentStaging).filter(DocumentStaging.expires_at < func.now()).all()
    for entree in expires:
        if entree.stored_path and os.path.isfile(entree.stored_path):
            os.remove(entree.stored_path)
        db.delete(entree)
    if expires:
        db.commit()


def preparer_maj(db: Session, doc_id: str, current_user) -> Document:
    """Contrôles communs à l'aperçu et à la confirmation."""
    doc = get_document_vivant(db, doc_id)
    check_domain_write(doc.domaine, current_user)
    if maj_en_cours(doc):
        raise HTTPException(409, "Une mise à jour de ce document est déjà en cours.")
    return doc


def prochaine_version(db: Session, doc: Document) -> int:
    """``max + 1`` sur l'historique : une restauration ne réutilise jamais un numéro pris."""
    maxi = db.query(func.max(DocumentVersion.version)).filter(DocumentVersion.doc_id == doc.doc_id).scalar()
    return max(doc.version, maxi or 0) + 1


def get_version(db: Session, doc: Document, version: int) -> DocumentVersion:
    v = (
        db.query(DocumentVersion)
        .filter(DocumentVersion.doc_id == doc.doc_id, DocumentVersion.version == version)
        .first()
    )
    if v is None:
        raise HTTPException(404, f"Version v{version} introuvable")
    return v


def chemin_de_version(doc: Document, v: DocumentVersion) -> str | None:
    """Fichier archivé d'une version, ou None s'il a disparu du disque."""
    candidats = [
        v.stored_path,
        os.path.join(settings.documents_storage_path, doc.doc_id, f"v{v.version}", v.filename),
        os.path.join(settings.documents_storage_path, doc.doc_id, v.filename),
    ]
    return next((c for c in candidats if c and os.path.isfile(c)), None)


def compter_en_attente(db: Session, doc_id: str) -> int:
    """Réponses EN_ATTENTE liées au document, non encore obsolètes."""
    return (
        db.query(Reponse.id)
        .join(ReponseChunk, ReponseChunk.reponse_id == Reponse.id)
        .filter(
            ReponseChunk.doc_id == doc_id,
            Reponse.statut == "EN_ATTENTE",
            Reponse.obsolete.is_(False),
        )
        .distinct()
        .count()
    )


def analyser_sortante(doc: Document, nouveau_texte: str) -> dict | None:
    """Diff avec la version actuellement en ligne. None si la version courante est illisible."""
    chemin_courant = chemin_du_fichier(doc.doc_id, doc.filename, doc.stored_path)
    if chemin_courant is None:
        return None
    try:
        ancien_texte = texte_complet(extract_text(chemin_courant))
    except Exception:
        return None

    changements = analyser_changements(ancien_texte, nouveau_texte)
    return {
        "diff_analysable": True,
        "nb_unites": changements["nb_unites"],
        "nb_ajoutes": changements["nb_ajoutes"],
        "nb_retires": changements["nb_retires"],
        "extraits_ajoutes": changements["extraits_ajoutes"],
        "extraits_retires": changements["extraits_retires"],
        "unites": [
            {
                "sens": u["sens"],
                "extrait_avant": extrait(u["avant"] or ""),
                "extrait_apres": extrait(u["apres"] or ""),
            }
            for u in changements["unites"][:MAX_UNITES_AFFICHEES]
        ],
    }


def stager_et_analyser(
    db: Session,
    doc: Document,
    *,
    contents: bytes,
    filename: str,
    content_hash: str,
    description: str | None,
    user_id,
    restauree_depuis: int | None = None,
) -> dict:
    """Met le fichier en staging et annonce l'impact. Partagé par la mise à jour et la restauration."""
    purger_staging(db)

    os.makedirs(STAGING_DIR, exist_ok=True)
    staging_id = uuid.uuid4()
    chemin = os.path.join(STAGING_DIR, f"{staging_id}_{filename}")
    with open(chemin, "wb") as f:
        f.write(contents)

    version_cible = prochaine_version(db, doc)
    anciens = capturer_chunks(doc.doc_id, version_cible)
    nouveau_texte = texte_complet(extract_text(chemin))
    indices = indices_modifies(anciens, nouveau_texte)
    nb_en_attente = compter_en_attente(db, doc.doc_id)
    changements = analyser_sortante(doc, nouveau_texte)

    prioritaires = racines(reponses_obsoletes(db, doc.doc_id, indices, version=doc.version))
    a_analyser = (
        racines(reponses_obsoletes(db, doc.doc_id, None))
        if changements is not None and changements["nb_unites"]
        else []
    )

    ids_prioritaires = {r.id for r in prioritaires}
    a_analyser.sort(key=lambda r: (r.id in ids_prioritaires, r.canonique, r.nb_validations or 0), reverse=True)

    db.add(
        DocumentStaging(
            id=staging_id,
            doc_id=doc.doc_id,
            user_id=user_id,
            stored_path=chemin,
            filename=filename,
            content_hash=content_hash,
            nb_obsoletes=len(prioritaires),
            restauree_depuis=restauree_depuis,
            expires_at=datetime.now(timezone.utc) + STAGING_TTL,
        )
    )
    db.commit()

    return {
        "staging_id": str(staging_id),
        "filename": filename,
        "version_cible": version_cible,
        "restauree_depuis": restauree_depuis,
        "nb_chunks_modifies": len(indices),
        "nb_total_chunks": len(anciens),
        "nb_en_attente": nb_en_attente,
        "nb_prioritaires": len(prioritaires),
        "nb_a_analyser": len(a_analyser),
        "nb_canoniques": sum(1 for r in a_analyser if r.canonique),
        "items": [item_impact(db, r, doc.doc_id, indices, anciens, doc.version) for r in prioritaires],
        "a_analyser": items_a_analyser(db, a_analyser)[:MAX_A_RELIRE],
        **(changements or MUET),
    }
