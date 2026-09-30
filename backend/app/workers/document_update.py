"""Document content replacement at constant ``doc_id``. Scroll BEFORE delete (Qdrant sole chunk source post-commit)"""

import logging
import os
import uuid
from datetime import datetime, timezone

from qdrant_client.models import (
    FieldCondition,
    Filter,
    FilterSelector,
    MatchValue,
    PointStruct,
    SparseVector,
)

from app.database import SessionLocal
from app.models.document import Document
from app.models.document_upload import DocumentUpload
from app.models.document_version import DocumentVersion
from app.services.broadcast import broadcast_sync
from app.services.contextualisation import contextualiser, synopsis, texte_indexe
from app.services.embedding import embed_texts
from app.services.obsolescence import (
    RAISON_ILLISIBLE,
    RAISON_INDISPONIBLE,
    RAISON_MAJ,
    analyser_changements,
    flaguer_en_analyse,
    indices_modifies,
    perimer_en_attente,
    poser_a_relire,
    racines,
    reponses_obsoletes,
    requeuer_en_attente,
)
from app.services.qdrant import COLLECTION_NAME, capturer_chunks, client, filtre_anciens
from app.services.reverification import signaler_voisines
from app.services.text_processing import chunk_text, extract_text, texte_complet
from app.workers.celery_app import celery_app
from app.workers.ingestion import chemin_du_fichier, point_id, store_file

logger = logging.getLogger(__name__)

JUSTIF_ILLISIBLE_VOISINE = (
    "Ancienne version du document illisible, aucun diff possible ; réponse proche du document sans le citer : "
    "à vérifier à la main."
)


def analyser_sortante(chemin_sortant: str | None, nouveau_texte: str) -> dict | None:
    """Diff avec la version sortante. None = fichier disparu ou corrompu (backfilled docs)."""
    if chemin_sortant is None:
        return None
    try:
        ancien_texte = texte_complet(extract_text(chemin_sortant))
    except Exception as exc:
        logger.warning("version sortante illisible (%s) — signalement dégradé", exc)
        return None

    return analyser_changements(ancien_texte, nouveau_texte)


class TacheMaj(celery_app.Task):
    """Last-resort net: unhandled failure would leave the document locked in EN_MAJ indefinitely."""

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        # version stays unchanged: old indexing is still in place (delete only happens after a successful upsert)
        doc_id = kwargs.get("doc_id")
        if doc_id:
            db = SessionLocal()
            try:
                doc = db.query(Document).filter(Document.doc_id == doc_id).first()
                if doc is not None and doc.statut == "EN_MAJ":
                    if doc.version == kwargs.get("new_version"):
                        # switched but follow-ups lost: no re-verification will ever clear these flags
                        from app.workers.reverification import JUSTIF_PANNE, rabattre  # noqa: PLC0415 — anti-circulaire

                        nb = rabattre(db, doc_id, doc.version, RAISON_INDISPONIBLE, JUSTIF_PANNE)
                        logger.error("v%d basculée sans ses suites — %d réponse(s) en relecture", doc.version, nb)
                    doc.statut = "ACTIF"
                    doc.update_job_id = None
                    doc.update_started_at = None
                    db.commit()
            finally:
                db.close()

        fichier = kwargs.get("file_path")
        if fichier and os.path.exists(fichier):
            os.remove(fichier)


@celery_app.task(
    name="document_update_job",
    base=TacheMaj,
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    queue="queue_ingestion",
)
def document_update_job(
    self,
    doc_id: str,
    new_version: int,
    file_path: str,
    filename: str,
    description: str = "",
    content_hash: str = "",
    uploaded_by: str | None = None,
    restauree_depuis: int | None = None,
):
    # new_version reserved by endpoint and passed as-is — recomputing it here would create orphaned versions on retry
    logger.info("mise à jour : %s (doc %s → v%d)", filename, doc_id, new_version)

    try:
        db = SessionLocal()
        try:
            doc = db.query(Document).filter(Document.doc_id == doc_id).first()
            if doc is None:
                raise ValueError(f"Document introuvable : {doc_id}")
            if doc.version == new_version:
                if doc.statut != "EN_MAJ":
                    logger.info("v%d déjà en place — rien à faire", new_version)
                    return {"statut": "OK", "doc_id": doc_id, "version": new_version, "nb_a_analyser": 0}
                # Switched but still locked: a retry after the commit. Concluding « already done » here dropped the
                # re-verification and the EN_ATTENTE drafts' withdrawal, silently — replay the follow-ups instead.
                logger.warning("v%d en place mais suites interrompues — reprise", new_version)
                replay = True
            else:
                replay = False
            domaine = doc.domaine
            chemin_sortant = chemin_du_fichier(doc.doc_id, doc.filename, doc.stored_path)  # read here — session closes
        finally:
            db.close()

        if replay:
            return _terminer(doc_id, new_version, file_path, self.request.id)

        # Capture du texte sortant impérativement avant toute suppression.
        anciens = capturer_chunks(doc_id, new_version)
        logger.info("%d chunks de la version sortante capturés", len(anciens))

        # Purge défensive d'un retry partiel (points déjà écrits en v{new}).
        client.delete(
            collection_name=COLLECTION_NAME,
            points_selector=FilterSelector(
                filter=Filter(
                    must=[
                        FieldCondition(key="doc_id", match=MatchValue(value=doc_id)),
                        FieldCondition(key="version", match=MatchValue(value=new_version)),
                    ]
                )
            ),
        )

        # Détection d'impact : ni chunking ni embedding requis.
        pages = extract_text(file_path)
        nouveau_texte = texte_complet(pages)
        indices = indices_modifies(anciens, nouveau_texte)
        logger.info("%d/%d passages modifiés", len(indices), len(anciens))

        # Fichier sortant encore sur disque : store_file écrit sous v{new_version}, il ne l'écrase pas.
        changements = analyser_sortante(chemin_sortant, nouveau_texte)
        if changements is None:
            logger.warning("contenu comparé impossible — toutes les réponses seront à relire")
        else:
            logger.info("%d unité(s) de changement", changements["nb_unites"])

        chunks = chunk_text(pages)
        contextes = contextualiser(chunks, synopsis(nouveau_texte, filename, description))
        embeddings = embed_texts(
            [texte_indexe(chunk, ctx) for chunk, ctx in zip(chunks, contextes, strict=True)],
            is_query=False,
        )
        logger.info("%d chunks embarqués, %d contextualisés", len(chunks), sum(1 for c in contextes if c))

        stored_path = store_file(file_path, doc_id, filename, new_version)

        # Upsert AVANT suppression : zéro trou de service.
        points = [
            PointStruct(
                id=point_id(doc_id, new_version, i),
                vector={
                    "dense": emb["dense"],
                    "sparse": SparseVector(
                        indices=emb["sparse"]["indices"],
                        values=emb["sparse"]["values"],
                    ),
                },
                payload={
                    "doc_id": doc_id,
                    "version": new_version,
                    "chunk_index": i,
                    "source": filename,
                    "domaine": domaine,
                    "contenu": chunk,  # raw, not texte_indexe — LLM prefix would make every chunk look modified at
                    "contexte": ctx,
                    "stored_path": stored_path,
                    "description": description,
                    "content_hash": content_hash,
                    "uploaded_by": uploaded_by,
                },
            )
            for i, (chunk, ctx, emb) in enumerate(zip(chunks, contextes, embeddings, strict=False))
        ]
        client.upsert(collection_name=COLLECTION_NAME, points=points)
        logger.info("%d points v%d indexés", len(points), new_version)

        client.delete(
            collection_name=COLLECTION_NAME,
            points_selector=FilterSelector(filter=filtre_anciens(doc_id, new_version)),
        )

        db = SessionLocal()
        try:
            user_uuid = uuid.UUID(uploaded_by) if uploaded_by else None
            doc = db.query(Document).filter(Document.doc_id == doc_id).first()
            ancienne_version = doc.version

            db.query(DocumentVersion).filter(
                DocumentVersion.doc_id == doc_id,
                DocumentVersion.remplacee_at.is_(None),
            ).update({"remplacee_at": datetime.now(timezone.utc)}, synchronize_session=False)

            ligne = (
                db.query(DocumentVersion)
                .filter(DocumentVersion.doc_id == doc_id, DocumentVersion.version == new_version)
                .first()
            )
            if ligne is None:
                ligne = DocumentVersion(doc_id=doc_id, version=new_version)
                db.add(ligne)
            ligne.filename = filename
            ligne.content_hash = content_hash or None
            ligne.stored_path = stored_path
            ligne.nb_chunks = len(chunks)
            ligne.taille_octets = os.path.getsize(stored_path) if os.path.isfile(stored_path) else None
            ligne.uploaded_by = user_uuid
            ligne.restauree_depuis = restauree_depuis
            ligne.remplacee_at = None
            # the version row carries what the follow-ups need: a retry after the commit can no longer recompute it
            # (the outgoing chunks are gone from Qdrant).
            ligne.changements = (
                None
                if changements is None
                else {**changements, "indices_disparus": sorted(indices), "version_sortante": ancienne_version}
            )

            doc.version = new_version
            doc.filename = filename
            doc.description = description
            doc.content_hash = content_hash or None
            doc.stored_path = stored_path
            doc.nb_chunks = len(chunks)
            doc.uploaded_by = user_uuid or doc.uploaded_by
            # lifted by _terminer only: while EN_MAJ, a retry knows the follow-ups are still owed.
            doc.statut = "EN_MAJ"

            db.add(DocumentUpload(doc_id=doc_id, user_id=user_uuid, domaine=domaine, filename=filename))

            # Flags in the switch's own commit: once v{new} is served, the responses citing it are under analysis
            # (or up for review), whatever fails afterwards. Disjoint from the EN_ATTENTE withdrawal (VALIDÉE/
            # CORRIGÉE only), so the order that once mattered no longer does.
            if changements is None:
                poser_a_relire(reponses_obsoletes(db, doc_id, indices=None), RAISON_ILLISIBLE, doc_id, new_version)
            elif changements["nb_unites"]:
                flaguer_en_analyse(db, doc_id, new_version)
            db.commit()
            logger.info("v%d → v%d basculé", ancienne_version, new_version)
        finally:
            db.close()

        return _terminer(doc_id, new_version, file_path, self.request.id)

    except Exception as exc:
        logger.error("erreur document_update_job '%s' : %s", filename, exc)
        raise self.retry(exc=exc) from exc


def _terminer(doc_id: str, version: int, file_path: str, job_id: str | None) -> dict:
    """Follow-ups of the switch, replayable: a retry after the commit comes back here. Everything read from the
    database — the version row holds the diff. The lock is lifted last: while EN_MAJ, a retry still owes this."""
    db = SessionLocal()
    try:
        doc = db.query(Document).filter(Document.doc_id == doc_id).first()
        ligne = (
            db.query(DocumentVersion)
            .filter(DocumentVersion.doc_id == doc_id, DocumentVersion.version == version)
            .first()
        )
        changements = ligne.changements if ligne else None
        domaine = doc.domaine

        # EN_ATTENTE : jamais servies, renvoyer au RAG plutôt que demander à un humain de juger.
        if changements is None or changements["nb_unites"]:
            requeuer_en_attente(db, perimer_en_attente(db, doc_id, RAISON_MAJ, version))

        # Re-verification enqueued whenever something changed, not only when a response cites the document: a
        # change can contradict a canonical built on another document, or written by hand — only the neighbour
        # search reaches those.
        analyse = changements is not None and bool(changements["nb_unites"])
        if analyse:
            from app.workers.reverification import reverification_job  # noqa: PLC0415 — anti-circulaire

            reverification_job.apply_async(
                kwargs={
                    "doc_id": doc_id,
                    "version": version,
                    "domaine": domaine,
                    "indices_disparus": changements.get("indices_disparus") or [],
                    # the version those indices belong to — None on jobs enqueued before this field existed
                    "version_sortante": changements.get("version_sortante"),
                },
                queue="queue_questions",
            )

        # No diff, no re-verification: the neighbours' only way to review (citing ones were flagged at the switch).
        voisines = (
            signaler_voisines(db, doc_id, version, domaine, RAISON_ILLISIBLE, JUSTIF_ILLISIBLE_VOISINE)
            if changements is None
            else []
        )

        citantes = reponses_obsoletes(db, doc_id, indices=None)
        nb_a_analyser = len(racines(citantes)) if analyse else 0
        nb_a_relire = len(racines(citantes + voisines)) if changements is None else 0

        doc.statut = "ACTIF"
        doc.update_job_id = None
        doc.update_started_at = None
        db.commit()
        filename, nb_chunks, stored_path = doc.filename, doc.nb_chunks, doc.stored_path
    finally:
        db.close()

    # Le staging n'a plus d'utilité : plus aucun retry ne suivra.
    if os.path.exists(file_path):
        os.remove(file_path)

    logger.info("v%d : %d à analyser, %d à relire", version, nb_a_analyser, nb_a_relire)

    broadcast_sync(
        f"sse:domain:{domaine}",
        "document_updated",
        {
            "doc_id": doc_id,
            "version": version,
            "filename": filename,
            "nb_chunks": nb_chunks,
            "nb_a_analyser": nb_a_analyser,
            "nb_a_relire": nb_a_relire,
            "job_id": job_id,
        },
    )

    return {
        "statut": "OK",
        "doc_id": doc_id,
        "filename": filename,
        "version": version,
        "stored_path": stored_path,
        "nb_chunks": nb_chunks,
        "nb_a_analyser": nb_a_analyser,
        "nb_a_relire": nb_a_relire,
    }
