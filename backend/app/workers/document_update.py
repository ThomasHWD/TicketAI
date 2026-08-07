"""Remplacement du contenu d'un document existant, à ``doc_id`` constant.

La difficulté n'est pas la ré-indexation : c'est de **capturer le texte de la
version sortante avant de la détruire**. Qdrant est la seule source du texte des
chunks qui ont fondé les réponses validées ; une fois les points supprimés,
plus aucun calcul d'obsolescence n'est possible. D'où l'ordre imposé ci-dessous.

Séquence :

::

    scroll (capture)  →  extract + indices_modifies  →  chunk + embed
                                                              ↓
    marquer_obsoletes  ←  commit Postgres  ←  delete anciens  ←  upsert nouveaux

L'upsert précède la suppression : l'ordre inverse ouvrirait un trou de service de
plusieurs dizaines de secondes (la durée de l'embedding) pendant lequel le
document ne répondrait plus. Le prix est une fenêtre de quelques centaines de ms
où les deux versions coexistent dans l'index.
"""

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
from app.services.obsolescence import RAISON_MAJ, indices_modifies, marquer_obsoletes, racines
from app.services.qdrant import COLLECTION_NAME, client
from app.workers.celery_app import celery_app
from app.workers.ingestion import chunk_text, extract_text, point_id, store_file


def filtre_anciens(doc_id: str, version_cible: int) -> Filter:
    """Les points du document qui ne sont pas ceux de la version en cours d'écriture.

    Deux clauses, toutes deux indispensables :

    * ``must=[doc_id]`` — les points de ``feedback_job`` (réponses canoniques) vivent
      dans la même collection ; un filtre plus large les effacerait ;
    * ``must_not=[version == cible]`` plutôt qu'un ``Range(lt=cible)`` — les documents
      backfillés n'ont **aucune** clé ``version`` dans leur payload, et un ``Range``
      sur clé absente ne matche pas : leurs chunks survivraient et le document
      resterait indexé en double.

    Utilisé pour la capture *et* pour la suppression : les deux portent ainsi sur
    exactement le même ensemble, y compris en présence d'un retry partiel.
    """
    return Filter(
        must=[FieldCondition(key="doc_id", match=MatchValue(value=doc_id))],
        must_not=[FieldCondition(key="version", match=MatchValue(value=version_cible))],
    )


def capturer_chunks(doc_id: str, version_cible: int) -> dict[int, str]:
    """``{chunk_index: contenu}`` de la version sortante, lu dans Qdrant.

    À appeler **avant toute suppression** : c'est la seule source du texte sortant.
    """
    anciens: dict[int, str] = {}
    offset = None
    while True:
        points, offset = client.scroll(
            collection_name=COLLECTION_NAME,
            scroll_filter=filtre_anciens(doc_id, version_cible),
            with_payload=["chunk_index", "contenu"],
            with_vectors=False,
            limit=256,
            offset=offset,
        )
        for p in points:
            if p.payload and p.payload.get("chunk_index") is not None:
                anciens[p.payload["chunk_index"]] = p.payload.get("contenu") or ""
        if offset is None:
            break
    return anciens


def texte_complet(pages: list[str]) -> str:
    """Le texte tel que ``chunk_text`` le verra — donc celui où chercher les passages."""
    return "\n\n".join(pages)


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
    print(f"♻️  --- MISE À JOUR DE '{filename}' (doc {doc_id} → v{new_version}) ---")

    try:
        db = SessionLocal()
        try:
            doc = db.query(Document).filter(Document.doc_id == doc_id).first()
            if doc is None:
                raise ValueError(f"Document introuvable : {doc_id}")
            # Reprise : le job a déjà abouti, un retry ne doit rien refaire.
            if doc.version == new_version:
                print(f"[MAJ] v{new_version} déjà en place — rien à faire")
                return {"statut": "OK", "doc_id": doc_id, "version": new_version, "nb_obsoletes": 0}
            domaine = doc.domaine
        finally:
            db.close()

        # Étape 1 — Capture du texte sortant, impérativement avant toute suppression
        anciens = capturer_chunks(doc_id, new_version)
        print(f"[MAJ] {len(anciens)} chunks de la version sortante capturés")

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
        indices = indices_modifies(anciens, texte_complet(pages))
        print(f"[MAJ] {len(indices)}/{len(anciens)} passages modifiés")

        # Étape 4 — Chunking + embedding de la nouvelle version
        chunks = chunk_text(pages)
        embeddings = embed_texts(chunks, is_query=False)
        print(f"[MAJ] {len(chunks)} chunks embarqués")

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
        print(f"[MAJ] {len(points)} points v{new_version} indexés")

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

            # Étape 9 — Obsolescence, une fois la nouvelle version bien en place
            obsoletes = marquer_obsoletes(db, doc_id, RAISON_MAJ, version=new_version, indices=indices)
            nb_obsoletes = len(racines(obsoletes))
        finally:
            db.close()

        # Étape 10 — Le staging n'a plus d'utilité : plus aucun retry ne suivra
        if os.path.exists(file_path):
            os.remove(file_path)

        print(f"[MAJ] ✅ v{ancienne_version} → v{new_version}, {nb_obsoletes} réponse(s) obsolète(s)")

        broadcast_sync(
            f"sse:domain:{domaine}",
            "document_updated",
            {
                "doc_id": doc_id,
                "version": new_version,
                "filename": filename,
                "nb_chunks": len(chunks),
                "nb_obsoletes": nb_obsoletes,
                "job_id": self.request.id,
            },
        )

        return {
            "statut": "OK",
            "doc_id": doc_id,
            "filename": filename,
            "version": new_version,
            "stored_path": stored_path,
            "nb_chunks": len(chunks),
            "nb_obsoletes": nb_obsoletes,
        }

    except Exception as exc:
        print(f"[MAJ] ❌ Erreur : {exc}")
        raise self.retry(exc=exc) from exc


