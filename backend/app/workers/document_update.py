"""Remplacement du contenu d'un document existant, à ``doc_id`` constant.

La difficulté n'est pas la ré-indexation : c'est de **capturer le texte de la
version sortante avant de la détruire**. Qdrant est la seule source du texte des
chunks qui ont fondé les réponses validées ; une fois les points supprimés,
plus aucune comparaison entre versions n'est possible. D'où l'ordre imposé
ci-dessous.

Séquence :

::

    scroll (capture)  →  extract + diff  →  chunk + embed
                                                  ↓
    flaguer_en_analyse  ←  commit Postgres  ←  delete anciens  ←  upsert nouveaux
            ↓
    reverification_job (queue_questions, asynchrone)

L'upsert précède la suppression : l'ordre inverse ouvrirait un trou de service de
plusieurs dizaines de secondes (la durée de l'embedding) pendant lequel le
document ne répondrait plus. Le prix est une fenêtre de quelques centaines de ms
où les deux versions coexistent dans l'index.

**Ce job ne périme plus aucune réponse validée.** Il calcule le diff, le fige sur
la version, marque les réponses concernées « analyse en cours » et passe la main :
décider qu'une réponse est contredite demande de la lire, ce que fait
``workers/reverification.py``. Seules les EN_ATTENTE sont périmées ici — elles
n'ont jamais été servies et repassent au RAG sans que personne ait à trancher.
"""

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
from app.services.embedding import embed_texts
from app.services.obsolescence import (
    RAISON_ILLISIBLE,
    RAISON_MAJ,
    analyser_changements,
    flaguer_en_analyse,
    indices_modifies,
    marquer_a_relire,
    perimer_en_attente,
    racines,
    requeuer_en_attente,
)
from app.services.qdrant import COLLECTION_NAME, capturer_chunks, client, filtre_anciens
from app.services.text_processing import chunk_text, extract_text, texte_complet
from app.workers.celery_app import celery_app
from app.workers.ingestion import chemin_du_fichier, point_id, store_file

logger = logging.getLogger(__name__)


def analyser_sortante(chemin_sortant: str | None, nouveau_texte: str) -> dict | None:
    """Le diff avec la version sortante, lue sur le disque.

    Renvoie ``None`` quand la version sortante est illisible — fichier disparu
    (documents backfillés) ou archive corrompue. **Ne jamais** reconstituer le
    texte sortant en concaténant les chunks capturés — le chevauchement de 128
    tokens du splitter fabriquerait une fausse suppression à chaque couture.
    """
    if chemin_sortant is None:
        return None
    try:
        ancien_texte = texte_complet(extract_text(chemin_sortant))
    except Exception as exc:
        logger.warning("version sortante illisible (%s) — signalement dégradé", exc)
        return None

    return analyser_changements(ancien_texte, nouveau_texte)


class TacheMaj(celery_app.Task):
    """Porte le ``on_failure`` : sans lui, un échec laisserait le document
    verrouillé en ``EN_MAJ`` **définitivement**, sans aucune voie de sortie."""

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Appelé une fois les retries épuisés (un ``Retry`` ne passe pas par ici).

        La version reste **inchangée** : l'ancienne indexation est toujours en place,
        la suppression des anciens points n'ayant lieu qu'après un upsert réussi.
        Ne couvre pas le worker tué net — d'où le garde-fou des 30 minutes côté API.
        """
        doc_id = kwargs.get("doc_id")
        if doc_id:
            db = SessionLocal()
            try:
                doc = db.query(Document).filter(Document.doc_id == doc_id).first()
                if doc is not None and doc.statut == "EN_MAJ":
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
    # `new_version` est réservé par l'endpoint et transmis tel quel : le recalculer
    # ici ferait choisir un numéro différent à chaque retry, laissant derrière lui
    # autant de versions orphelines dans Qdrant.
    logger.info("mise à jour : %s (doc %s → v%d)", filename, doc_id, new_version)

    try:
        db = SessionLocal()
        try:
            doc = db.query(Document).filter(Document.doc_id == doc_id).first()
            if doc is None:
                raise ValueError(f"Document introuvable : {doc_id}")
            # Reprise : le job a déjà abouti, un retry ne doit rien refaire.
            if doc.version == new_version:
                logger.info("v%d déjà en place — rien à faire", new_version)
                return {"statut": "OK", "doc_id": doc_id, "version": new_version, "nb_a_analyser": 0}
            domaine = doc.domaine
            # Le chemin du fichier sortant se lit ici, pas plus loin : la session
            # ferme dans deux lignes et `doc` devient détaché.
            chemin_sortant = chemin_du_fichier(doc.doc_id, doc.filename, doc.stored_path)
        finally:
            db.close()

        # Étape 1 — Capture du texte sortant, impérativement avant toute suppression
        anciens = capturer_chunks(doc_id, new_version)
        logger.info("%d chunks de la version sortante capturés", len(anciens))

        # Étape 2 — Purge défensive d'un retry partiel (points déjà écrits en v{new})
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

        # Étape 3 — Extraction et détection d'impact (ni chunking ni embedding requis)
        pages = extract_text(file_path)
        nouveau_texte = texte_complet(pages)
        indices = indices_modifies(anciens, nouveau_texte)
        logger.info("%d/%d passages modifiés", len(indices), len(anciens))

        # Le fichier sortant est encore sur le disque : `store_file` (étape 5)
        # écrit sous v{new_version}, il ne l'écrase pas.
        changements = analyser_sortante(chemin_sortant, nouveau_texte)
        if changements is None:
            logger.warning("contenu comparé impossible — toutes les réponses seront à relire")
        else:
            logger.info("%d unité(s) de changement", changements["nb_unites"])

        # Étape 4 — Chunking + embedding de la nouvelle version
        chunks = chunk_text(pages)
        embeddings = embed_texts(chunks, is_query=False)
        logger.info("%d chunks embarqués", len(chunks))

        # Étape 5 — Archivage du fichier sous v{new_version}
        stored_path = store_file(file_path, doc_id, filename, new_version)

        # Étape 6 — Upsert AVANT suppression : zéro trou de service
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
                    "contenu": chunk,
                    "stored_path": stored_path,
                    "description": description,
                    "content_hash": content_hash,
                    "uploaded_by": uploaded_by,
                },
            )
            for i, (chunk, emb) in enumerate(zip(chunks, embeddings, strict=False))
        ]
        client.upsert(collection_name=COLLECTION_NAME, points=points)
        logger.info("%d points v%d indexés", len(points), new_version)

        # Étape 7 — Suppression des points de toutes les versions antérieures
        client.delete(
            collection_name=COLLECTION_NAME,
            points_selector=FilterSelector(filter=filtre_anciens(doc_id, new_version)),
        )

        # Étape 8 — Bascule en base
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
            ligne.changements = changements

            doc.version = new_version
            doc.filename = filename
            doc.description = description
            doc.content_hash = content_hash or None
            doc.stored_path = stored_path
            doc.nb_chunks = len(chunks)
            doc.statut = "ACTIF"
            doc.update_job_id = None
            doc.update_started_at = None
            doc.uploaded_by = user_uuid or doc.uploaded_by

            db.add(DocumentUpload(doc_id=doc_id, user_id=user_uuid, domaine=domaine, filename=filename))
            db.commit()

            # Étape 9 — Les EN_ATTENTE bâties sur la version sortante. Aucun
            # jugement requis : jamais servies, jamais indexées, et les valider
            # plus tard publierait une réponse fondée sur un texte disparu.
            a_du_neuf = changements is None or bool(changements["nb_unites"])
            if a_du_neuf:
                requeuer_en_attente(db, perimer_en_attente(db, doc_id, RAISON_MAJ, new_version))

            # Étape 10 — Mise sous analyse. Après l'étape 9, jamais avant.
            if changements is None:
                nb_a_relire = len(racines(marquer_a_relire(db, doc_id, new_version, RAISON_ILLISIBLE)))
                nb_a_analyser = 0
            elif changements["nb_unites"]:
                nb_a_analyser = len(racines(flaguer_en_analyse(db, doc_id, new_version)))
                nb_a_relire = 0
            else:
                nb_a_relire = nb_a_analyser = 0
        finally:
            db.close()

        # Étape 11 — Le staging n'a plus d'utilité : plus aucun retry ne suivra
        if os.path.exists(file_path):
            os.remove(file_path)

        logger.info("v%d → v%d : %d à analyser, %d à relire", ancienne_version, new_version, nb_a_analyser, nb_a_relire)

        broadcast_sync(
            f"sse:domain:{domaine}",
            "document_updated",
            {
                "doc_id": doc_id,
                "version": new_version,
                "filename": filename,
                "nb_chunks": len(chunks),
                "nb_a_analyser": nb_a_analyser,
                "nb_a_relire": nb_a_relire,
                "job_id": self.request.id,
            },
        )

        # Étape 12 — La ré-vérification, sur `queue_questions`.
        if nb_a_analyser:
            from app.workers.reverification import reverification_job  # noqa: PLC0415 — anti-circulaire

            reverification_job.apply_async(
                kwargs={
                    "doc_id": doc_id,
                    "version": new_version,
                    "domaine": domaine,
                    "indices_disparus": sorted(indices),
                },
                queue="queue_questions",
            )

        return {
            "statut": "OK",
            "doc_id": doc_id,
            "filename": filename,
            "version": new_version,
            "stored_path": stored_path,
            "nb_chunks": len(chunks),
            "nb_a_analyser": nb_a_analyser,
            "nb_a_relire": nb_a_relire,
        }

    except Exception as exc:
        logger.error("erreur document_update_job '%s' : %s", filename, exc)
        raise self.retry(exc=exc) from exc
