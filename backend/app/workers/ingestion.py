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
    """Dossier d'archive d'une version : {storage}/{doc_id}/v{n}/."""
    return os.path.join(settings.documents_storage_path, doc_id, f"v{version}")


def chemin_du_fichier(doc_id: str, filename: str, stored_path: str | None) -> str | None:
    """Chemin sur disque du fichier courant d'un document, ou None s'il a disparu.

    Le repli couvre les documents backfillés, dont le fichier est resté à la racine
    du dossier ``{doc_id}`` au lieu d'un sous-dossier ``v{n}/``.

    Prend des chaînes plutôt qu'un ``Document`` : le job de mise à jour l'appelle
    après avoir fermé sa session, où l'instance est détachée. Et il vit ici plutôt
    que dans ``api/v1/documents.py``, qui importe déjà le job — l'inverse fermerait
    le cycle.
    """
    if stored_path and os.path.isfile(stored_path):
        return stored_path
    repli = os.path.join(settings.documents_storage_path, doc_id, filename)
    return repli if os.path.isfile(repli) else None


def store_file(tmp_path: str, doc_id: str, filename: str, version: int = 1) -> str:
    """Copie le fichier de /tmp vers le stockage permanent de la version.

    Copie et non déplacement : après un ``move`` réussi, un retry Celery échouerait
    sur ``extract_text`` (fichier disparu) et boucherait jusqu'à ``max_retries``.
    Le temporaire n'est supprimé qu'une fois le job abouti.
    """
    dest_dir = version_dir(doc_id, version)
    os.makedirs(dest_dir, exist_ok=True)
    dest_path = os.path.join(dest_dir, filename)
    shutil.copy2(tmp_path, dest_path)
    return dest_path


def point_id(doc_id: str, version: int, index: int) -> str:
    """Id de point déterministe : un retry réécrit les mêmes points au lieu d'en créer."""
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
    # doc_id vient de l'appelant : le régénérer ici ferait naître un document
    # différent à chaque retry, chacun laissant ses chunks derrière lui.
    doc_id = doc_id or str(uuid.uuid5(uuid.NAMESPACE_DNS, str(self.request.id)))
    version = 1

    try:
        logger.info("début de l'ingestion : %s", filename)

        # Étape 1 — Extraction
        pages = extract_text(file_path)
        logger.info("%d pages extraites", len(pages))

        # Étape 2 — Chunking
        chunks = chunk_text(pages)
        logger.info("%d chunks générés", len(chunks))

        texte = texte_complet(pages)

        # Étape 2 bis — Contextualisation : un locateur par chunk, indexé avec lui.
        # Un chunk isolé ne dit pas de quelle règle il relève (« les alternants
        # n'en bénéficient pas » ne contient pas le mot « télétravail ») ; c'est
        # ce préfixe qui le rend trouvable. Best-effort de bout en bout : la
        # liste fait toujours la longueur de `chunks`, remplie de `""` si Albert
        # est injoignable, et l'indexation retombe alors sur le texte brut.
        contextes = contextualiser(chunks, synopsis(texte, filename, description))
        logger.info("%d/%d chunks contextualisés", sum(1 for c in contextes if c), len(chunks))

        # Étape 3 — Embedding
        logger.info("embedding de %d chunks...", len(chunks))
        embeddings = embed_texts(
            [texte_indexe(chunk, ctx) for chunk, ctx in zip(chunks, contextes, strict=True)],
            is_query=False,
        )
        logger.info("embeddings générés")

        # Étape 4 — Stockage permanent, avant l'indexation : le chemin fait partie du
        # payload, l'écrire après imposerait un set_payload correctif et laisserait une
        # fenêtre où les points portent stored_path: None.
        stored_path = store_file(file_path, doc_id, filename, version)
        logger.info("fichier stocké : %s", stored_path)

        # Étape 5 — Indexation Qdrant (batch unique)
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
                        # `contenu` reste **brut**. Le préfixe vit à côté, jamais
                        # dedans : `capturer_chunks` lit `contenu` pour le diff
                        # d'une mise à jour, et une sortie de LLM varie d'une
                        # exécution à l'autre — chaque chunk paraîtrait modifié à
                        # chaque version. Le texte encodé se recompose par
                        # `texte_indexe(contenu, contexte)`, seule définition.
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

        # Étape 6 — Quelles réponses déjà servies ce document interpelle-t-il ?
        # Gratuit : `embeddings` est encore là, la détection ne coûte que des
        # requêtes Qdrant. Sous try/except parce qu'une ingestion réussie ne doit
        # pas échouer sur son propre effet de bord.
        try:
            cibles = cibles_confrontation(embeddings, domaine)
        except Exception as exc:
            logger.error("détection de confrontation impossible (%s) — ingestion poursuivie", exc)
            cibles = {}

        # Étape 7 — Enregistrement en base
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

            # `ANALYSE_EN_COURS` posé **dans le même commit** que les lignes de
            # document : entre la publication du document et le verdict il
            # s'écoule de trente secondes à quelques minutes, pendant lesquelles
            # les réponses continuent d'être servies. Elles le sont — mais plus
            # jamais sans que l'interface le dise.
            famille = familles_servies(db, identifiants(cibles))
            poser_a_relire(famille, RAISON_ANALYSE, doc_id, version)
            nb_a_analyser = len(racines(famille))

            db.commit()
        finally:
            db.close()

        # Étape 8 — Le temporaire n'a plus d'utilité : plus aucun retry ne suivra
        if os.path.exists(file_path):
            os.remove(file_path)

        # Étape 9 — La confrontation, sur `queue_questions` : de l'attente réseau
        # Albert, qui n'a rien à faire dans la file qui sérialise les ingestions.
        # Enfilée seulement s'il y a des cibles — sinon le job n'aurait rien à
        # résoudre, et `rabattre` balaierait un lot vide.
        if nb_a_analyser:
            from app.workers.confrontation import confrontation_job  # noqa: PLC0415 — anti-circulaire

            confrontation_job.apply_async(
                kwargs={"doc_id": doc_id, "version": version, "domaine": domaine, "cibles": cibles},
                queue="queue_questions",
            )
            # Sans cet événement l'onglet « À relire » ne se remplirait qu'au
            # prochain rafraîchissement manuel : `job_completed` est adressé au
            # seul déposant, et il n'est pas forcément validateur du domaine.
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
    """Crée (ou met à jour, si un retry est passé par là) les lignes documents/versions.

    ``changements`` est le résumé « tout est ajouté » de ``resume_ajout`` : sans
    lui, l'onglet « À relire » afficherait « le détail de cette mise à jour n'a
    pas été conservé » pour un document qui n'a jamais été mis à jour.
    """
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
