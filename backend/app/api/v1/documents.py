import hashlib
import os
import re
import shutil
import uuid
from datetime import datetime, timedelta, timezone
from typing import Annotated

from celery.result import AsyncResult
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from qdrant_client.models import FieldCondition, Filter, FilterSelector, MatchValue
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.core.permissions import check_domain_read, check_domain_write, user_domaines
from app.core.security import AdminUser, BackofficeUser, CurrentUser
from app.database import SessionLocal
from app.models.document import Document
from app.models.document_staging import DocumentStaging
from app.models.document_version import DocumentVersion
from app.models.groupe import Groupe
from app.models.reponse_chunk import ReponseChunk
from app.models.ticket import Ticket
from app.services.obsolescence import (
    RAISON_SUPPRESSION,
    indices_modifies,
    marquer_obsoletes,
    racines,
    reponses_obsoletes,
)
from app.services.qdrant import COLLECTION_NAME, client
from app.workers.celery_app import celery_app
from app.workers.document_update import capturer_chunks, document_update_job, texte_complet
from app.workers.ingestion import extract_text, ingestion_job

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


def valider_contenu(filename: str | None, contents: bytes) -> tuple[str, str]:
    """Valide un fichier téléversé et renvoie ``(nom assaini, content_hash)``.

    Factorisé entre la création d'un document et la mise à jour d'une version :
    sans ce point unique, les deux chemins de validation divergeraient.
    """
    filename = sanitize_filename(filename)
    ext = os.path.splitext(filename)[1].lower()
    if ext not in MAGIC_BYTES:
        raise HTTPException(400, f"Extension non supportée : {ext}")

    size_mb = len(contents) / (1024 * 1024)
    if size_mb > MAX_SIZE_MB:
        raise HTTPException(400, f"Fichier trop volumineux : {size_mb:.1f} Mo (max {MAX_SIZE_MB} Mo)")

    # Le Content-Type annoncé par le client est déclaratif, donc spoofable : on
    # vérifie la signature binaire réelle.
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
    force_nouveau: bool = False,
):
    # Validation domaine
    domaine = domaine.upper()
    domaines_valides = {r[0] for r in db.query(Groupe.domaine).distinct().all()}
    if not domaines_valides:
        raise HTTPException(400, "Aucun domaine configuré. Créez d'abord un groupe.")
    if domaine not in domaines_valides:
        raise HTTPException(400, f"Domaine invalide : {domaine}")
    check_domain_write(domaine, current_user)

    contents = await file.read()
    filename, content_hash = valider_contenu(file.filename, contents)

    # Détection de doublon via hash SHA-256 du contenu, dans le domaine visé seulement.
    # search_hybrid filtre strictement par domaine : un PDF ingéré en IT est invisible
    # en RH, l'ancien scroll global interdisait pourtant de l'y ingérer.
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

    # Garde-fou homonyme : même nom, même domaine, contenu différent — c'est très
    # probablement une nouvelle version. Sans ce contrôle, l'ingestion créait un
    # second document indépendant, et les deux versions se contredisaient en
    # répondant tour à tour. Le `detail` est structuré pour que le front puisse
    # proposer la mise à jour du document existant sans parser un message.
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


# ── Mise à jour d'un document : aperçu puis confirmation ──────────────────────
#
# Le calcul d'impact ne demande ni chunking ni embedding — seulement le texte
# extrait de la nouvelle version. L'aperçu peut donc être **exact** plutôt
# qu'estimatif, ce qui est la seule façon honnête d'annoncer « ces N réponses
# vont cesser d'être servies » avant de le faire.

STAGING_DIR = os.path.join(UPLOAD_DIR, "staging")
STAGING_TTL = timedelta(hours=1)
# Au-delà, un EN_MAJ est tenu pour un verrou abandonné : `on_failure` ne s'exécute
# pas quand le worker est tué net, et le document resterait bloqué à vie.
MAJ_PERIMEE_APRES = timedelta(minutes=30)
# Extrait de passage affiché dans l'écran d'impact.
LONGUEUR_EXTRAIT = 240


class ConfirmerMajRequest(BaseModel):
    staging_id: str


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
    """Supprime les aperçus expirés, fichier compris.

    Un aperçu affiché puis abandonné laisse sinon son fichier sur le disque
    indéfiniment — le code écrivait déjà des temporaires sans jamais nettoyer
    les échecs, ce ménage est dû de toute façon.
    """
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


@router.post("/documents/{doc_id}/versions/preview")
def previsualiser_maj(
    doc_id: str,
    current_user: BackofficeUser,
    file: Annotated[UploadFile, File(...)],
    db: DB,
    description: str | None = None,
):
    """Analyse l'impact d'un nouveau fichier **sans rien modifier**.

    Déclaré ``def`` et non ``async def`` à dessein : Starlette exécute alors la
    fonction dans son threadpool, et l'extraction PyMuPDF — bloquante, jusqu'à
    quelques secondes sur un gros PDF — ne gèle pas la boucle d'événements.
    """
    doc = preparer_maj(db, doc_id, current_user)

    contents = file.file.read()
    filename, content_hash = valider_contenu(file.filename, contents)

    # Identité avec la version en place : il n'y a rien à mettre à jour.
    # Neutralisé si `content_hash` est NULL (document backfillé) : on ne peut pas
    # prouver l'identité, donc on n'interdit pas — et on renseigne le hash au passage.
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
            Document.statut.in_(STATUTS_VIVANTS),
        )
        .first()
    )
    if autre:
        raise HTTPException(409, f"Ce contenu est déjà indexé sous « {autre.filename} » ({doc.domaine}).")

    purger_staging(db)

    os.makedirs(STAGING_DIR, exist_ok=True)
    staging_id = uuid.uuid4()
    chemin = os.path.join(STAGING_DIR, f"{staging_id}_{filename}")
    with open(chemin, "wb") as f:
        f.write(contents)

    version_cible = prochaine_version(db, doc)
    anciens = capturer_chunks(doc_id, version_cible)
    indices = indices_modifies(anciens, texte_complet(extract_text(chemin)))
    impactees = racines(reponses_obsoletes(db, doc_id, indices))

    db.add(
        DocumentStaging(
            id=staging_id,
            doc_id=doc_id,
            user_id=current_user.id,
            stored_path=chemin,
            filename=filename,
            content_hash=content_hash,
            description=(description if description is not None else doc.description) or "",
            nb_obsoletes=len(impactees),
            expires_at=datetime.now(timezone.utc) + STAGING_TTL,
        )
    )
    db.commit()

    return {
        "staging_id": str(staging_id),
        "filename": filename,
        "version_cible": version_cible,
        "nb_chunks_modifies": len(indices),
        "nb_total_chunks": len(anciens),
        "nb_obsoletes": len(impactees),
        "nb_canoniques": sum(1 for r in impactees if r.canonique),
        "items": [_item_impact(db, r, doc_id, indices, anciens) for r in impactees],
    }


def prochaine_version(db: Session, doc: Document) -> int:
    """``max + 1`` sur l'historique, et pas ``doc.version + 1``.

    Une restauration crée une version au-dessus de toutes les autres ; se fier au
    seul numéro courant finirait par réutiliser un numéro déjà pris.
    """
    maxi = (
        db.query(func.max(DocumentVersion.version)).filter(DocumentVersion.doc_id == doc.doc_id).scalar()
    )
    return max(doc.version, maxi or 0) + 1


def _item_impact(db: Session, reponse, doc_id: str, indices: set[int], anciens: dict[int, str]) -> dict:
    """Ligne de l'écran d'impact : la réponse, et les passages qui la fondaient.

    Une copie SUGGESTION/CANONIQUE ne cite aucun chunk : sa liste est vide, c'est
    sa source qui porte les passages. On l'affiche quand même — elle disparaîtra.
    """
    cites = {
        r[0]
        for r in db.query(ReponseChunk.chunk_index)
        .filter(ReponseChunk.reponse_id == reponse.id, ReponseChunk.doc_id == doc_id)
        .all()
    }
    modifies = sorted(cites & indices)
    ticket = db.query(Ticket).filter(Ticket.id == reponse.ticket_id).first()
    return {
        "reponse_id": str(reponse.id),
        "question": reponse.question_suivi or (ticket.question if ticket else ""),
        "canonique": reponse.canonique,
        "nb_validations": reponse.nb_validations,
        "chunks_modifies": modifies,
        "extraits": [_tronquer(anciens.get(i, "")) for i in modifies[:3]],
    }


def _tronquer(texte: str) -> str:
    texte = " ".join(texte.split())
    return texte if len(texte) <= LONGUEUR_EXTRAIT else texte[:LONGUEUR_EXTRAIT] + "…"


@router.post("/documents/{doc_id}/versions/confirm")
async def confirmer_maj(
    doc_id: str,
    payload: ConfirmerMajRequest,
    current_user: BackofficeUser,
    db: DB,
):
    """Réserve le numéro de version, pose le verrou, lance le job.

    Réponse de **même forme que l'upload** pour que le suivi de job côté front
    fonctionne sans adaptation.
    """
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

    # Lu avant la suppression de la ligne : après le `db.delete`, l'instance est
    # détachée et tout accès à ses attributs échoue.
    filename = staging.filename
    version_cible = prochaine_version(db, doc)
    doc.statut = "EN_MAJ"
    doc.update_started_at = datetime.now(timezone.utc)
    db.commit()

    # Tout en kwargs : /admin/documents/{task_id}/retry rejoue la tâche depuis
    # `meta["kwargs"]`, où les arguments positionnels sont invisibles.
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
    # L'aperçu a rempli son office ; le fichier, lui, appartient désormais au job,
    # qui le supprime en fin de course (ou via `on_failure`).
    db.delete(staging)
    db.commit()

    return {
        "job_id": job.id,
        "doc_id": doc_id,
        "filename": filename,
        "version": version_cible,
        "statut": "EN_ATTENTE",
    }


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
