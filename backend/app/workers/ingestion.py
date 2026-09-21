import logging
import os
import shutil
import uuid

from qdrant_client.models import PointStruct, SparseVector

from app.config import settings
from app.database import SessionLocal
from app.models.document import Document
from app.models.document_upload import DocumentUpload
from app.models.document_version import DocumentVersion
from app.services.broadcast import broadcast_sync
from app.services.confrontation import cibles_confrontation, familles_servies, identifiants, resume_ajout
from app.services.contextualisation import contextualiser, synopsis, texte_indexe
from app.services.embedding import embed_texts
from app.services.obsolescence import RAISON_ANALYSE, poser_a_relire, racines
from app.services.qdrant import COLLECTION_NAME, client
from app.services.text_processing import chunk_text, extract_text, texte_complet
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


def version_dir(doc_id: str, version: int) -> str:
    """Archive directory for a version: {storage}/{doc_id}/v{n}/."""
    return os.path.join(settings.documents_storage_path, doc_id, f"v{version}")


def chemin_du_fichier(doc_id: str, filename: str, stored_path: str | None) -> str | None:
    """Path to the current file on disk, or None if it has disappeared. Fallback covers backfilled documents whose"""
    if stored_path and os.path.isfile(stored_path):
        return stored_path
    repli = os.path.join(settings.documents_storage_path, doc_id, filename)
    return repli if os.path.isfile(repli) else None


def store_file(tmp_path: str, doc_id: str, filename: str, version: int = 1) -> str:
    """Copy (not move) the file to permanent storage — a move would cause retries to fail on extract_text (file"""
    dest_dir = version_dir(doc_id, version)
    os.makedirs(dest_dir, exist_ok=True)
    dest_path = os.path.join(dest_dir, filename)
    shutil.copy2(tmp_path, dest_path)
    return dest_path


def point_id(doc_id: str, version: int, index: int) -> str:
    """Deterministic point id — a retry rewrites the same points instead of creating duplicates."""
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{doc_id}:{version}:{index}"))


@celery_app.task(
    name="ingestion_job",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    queue="queue_ingestion",
)
def ingestion_job(
    self,
    file_path: str,
    filename: str,
    domaine: str,
    description: str = "",
    content_hash: str = "",
    uploaded_by: str | None = None,
    doc_id: str | None = None,
):
    # caller-provided doc_id — regenerating here would create a new document on every retry.
    doc_id = doc_id or str(uuid.uuid5(uuid.NAMESPACE_DNS, str(self.request.id)))
    version = 1

    try:
        logger.info("début de l'ingestion : %s", filename)

        pages = extract_text(file_path)
        logger.info("%d pages extraites", len(pages))

        chunks = chunk_text(pages)
        logger.info("%d chunks générés", len(chunks))

        texte = texte_complet(pages)

        # Locator prefix makes context-dependent chunks findable; list is always len(chunks) — "" on Albert failure
        contextes = contextualiser(chunks, synopsis(texte, filename, description))
        logger.info("%d/%d chunks contextualisés", sum(1 for c in contextes if c), len(chunks))

        logger.info("embedding de %d chunks...", len(chunks))
        embeddings = embed_texts(
            [texte_indexe(chunk, ctx) for chunk, ctx in zip(chunks, contextes, strict=True)],
            is_query=False,
        )
        logger.info("embeddings générés")

        # Stored before indexing — stored_path is part of the payload; writing it after would require a set_payload and
        stored_path = store_file(file_path, doc_id, filename, version)
        logger.info("fichier stocké : %s", stored_path)

        logger.info("indexation dans Qdrant...")
        points = []
        for i, (chunk, ctx, emb) in enumerate(zip(chunks, contextes, embeddings, strict=False)):
            points.append(
                PointStruct(
                    id=point_id(doc_id, version, i),
                    vector={
                        "dense": emb["dense"],
                        "sparse": SparseVector(
                            indices=emb["sparse"]["indices"],
                            values=emb["sparse"]["values"],
                        ),
                    },
                    payload={
                        "doc_id": doc_id,
                        "version": version,
                        "chunk_index": i,
                        "source": filename,
                        "domaine": domaine,
                        # contenu stays raw — contexte is LLM output (varies per run); folding it in would make every
                        "contenu": chunk,
                        "contexte": ctx,
                        "stored_path": stored_path,
                        "description": description,
                        "content_hash": content_hash,
                        "uploaded_by": uploaded_by,
                    },
                )
            )

        client.upsert(collection_name=COLLECTION_NAME, points=points)
        logger.info("%d points indexés dans Qdrant", len(points))

        # Free: embeddings already computed, only Qdrant queries needed.
        try:
            cibles = cibles_confrontation(embeddings, domaine)
        except Exception as exc:
            logger.error("détection de confrontation impossible (%s) — ingestion poursuivie", exc)
            cibles = {}

        db = SessionLocal()
        try:
            user_uuid = uuid.UUID(uploaded_by) if uploaded_by else None
            _enregistrer_document(
                db,
                doc_id=doc_id,
                version=version,
                filename=filename,
                domaine=domaine,
                description=description,
                content_hash=content_hash,
                stored_path=stored_path,
                nb_chunks=len(chunks),
                uploaded_by=user_uuid,
                changements=resume_ajout(texte),
            )
            db.add(
                DocumentUpload(
                    doc_id=doc_id,
                    user_id=user_uuid,
                    domaine=domaine,
                    filename=filename,
                )
            )

            # ANALYSE_EN_COURS flagged in same commit — closes the race window between document publication and verdict.
            famille = familles_servies(db, identifiants(cibles))
            poser_a_relire(famille, RAISON_ANALYSE, doc_id, version)
            nb_a_analyser = len(racines(famille))

            db.commit()
        finally:
            db.close()

        if os.path.exists(file_path):
            os.remove(file_path)

        # confrontation on queue_questions: Albert network waits have nothing to do in the ingestion queue.
        if nb_a_analyser:
            from app.workers.confrontation import confrontation_job  # noqa: PLC0415 — anti-circular

            confrontation_job.apply_async(
                kwargs={"doc_id": doc_id, "version": version, "domaine": domaine, "cibles": cibles},
                queue="queue_questions",
            )
            # required: job_completed targets the uploader only, not domain validators.
            broadcast_sync(
                f"sse:domain:{domaine}",
                "reverification_started",
                {"doc_id": doc_id, "version": version, "nb_a_analyser": nb_a_analyser},
            )
            logger.info("%d réponse(s) servie(s) à confronter au nouveau document", nb_a_analyser)

        result = {
            "statut": "OK",
            "filename": filename,
            "doc_id": doc_id,
            "stored_path": stored_path,
            "nb_chunks": len(chunks),
            "nb_a_analyser": nb_a_analyser,
        }

        if uploaded_by:
            broadcast_sync(
                f"sse:user:{uploaded_by}",
                "job_completed",
                {"job_id": self.request.id, "status": "SUCCESS", "nb_chunks": len(chunks)},
            )

        return result

    except Exception as exc:
        logger.error("erreur ingestion '%s' : %s", filename, exc)
        if self.request.retries >= self.max_retries and uploaded_by:
            broadcast_sync(
                f"sse:user:{uploaded_by}",
                "job_completed",
                {"job_id": self.request.id, "status": "FAILURE", "erreur": str(exc)},
            )
        raise self.retry(exc=exc) from exc


def _enregistrer_document(
    db, *, doc_id, version, filename, domaine, description, content_hash, stored_path, nb_chunks, uploaded_by,
    changements=None,
) -> None:
    """Create or update document/version rows. changements prevents 'update history not preserved' in À-relire for a"""
    doc = db.query(Document).filter(Document.doc_id == doc_id).first()
    if doc is None:
        doc = Document(doc_id=doc_id)
        db.add(doc)
    doc.version = version
    doc.filename = filename
    doc.domaine = domaine
    doc.description = description
    doc.content_hash = content_hash or None
    doc.stored_path = stored_path
    doc.nb_chunks = nb_chunks
    doc.statut = "ACTIF"
    doc.uploaded_by = uploaded_by

    ligne = (
        db.query(DocumentVersion).filter(DocumentVersion.doc_id == doc_id, DocumentVersion.version == version).first()
    )
    if ligne is None:
        ligne = DocumentVersion(doc_id=doc_id, version=version)
        db.add(ligne)
    ligne.filename = filename
    ligne.content_hash = content_hash or None
    ligne.stored_path = stored_path
    ligne.nb_chunks = nb_chunks
    ligne.taille_octets = os.path.getsize(stored_path) if os.path.isfile(stored_path) else None
    ligne.uploaded_by = uploaded_by
    ligne.changements = changements
