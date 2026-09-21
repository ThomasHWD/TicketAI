import logging

from app.config import settings
from qdrant_client import QdrantClient
from qdrant_client.http.exceptions import UnexpectedResponse
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    Modifier,
    SparseIndexParams,
    SparseVectorParams,
    VectorParams,
)

logger = logging.getLogger(__name__)

client = QdrantClient(host=settings.qdrant_host, port=settings.qdrant_port)

# conftest forces a `_test` suffix before import; consumers import by value so env must be set before import time
COLLECTION_NAME = settings.qdrant_collection


def init_collection():
    if client.collection_exists(collection_name=COLLECTION_NAME):
        logger.info("Collection '%s' existe déjà.", COLLECTION_NAME)
    else:
        try:
            client.create_collection(
                collection_name=COLLECTION_NAME,
                vectors_config={
                    "dense": VectorParams(
                        size=1024,  # BGE-M3
                        distance=Distance.COSINE,
                    )
                },
                # Modifier.IDF: Qdrant supplies server-side IDF; bm25.py only provides token indices + TF saturation.
                # Fixed at collection creation — existing collections without it must be recreated.
                sparse_vectors_config={
                    "sparse": SparseVectorParams(
                        index=SparseIndexParams(on_disk=False),
                        modifier=Modifier.IDF,
                    )
                },
            )
            logger.info("Collection '%s' créée.", COLLECTION_NAME)
        except UnexpectedResponse as exc:
            # collection_exists() + create_collection() is not atomic — 409 = another worker won the race
            if exc.status_code != 409:
                raise
            logger.info("Collection '%s' créée en parallèle par un autre worker.", COLLECTION_NAME)

    # Index payload pour le filtrage par domaine (idempotent)
    client.create_payload_index(
        collection_name=COLLECTION_NAME,
        field_name="domaine",
        field_schema="keyword",
    )
    logger.debug("Index payload 'domaine' assuré.")

    # Index payload pour la détection de doublons par hash (idempotent)
    client.create_payload_index(
        collection_name=COLLECTION_NAME,
        field_name="content_hash",
        field_schema="keyword",
    )
    logger.debug("Index payload 'content_hash' assuré.")

    client.create_payload_index(
        collection_name=COLLECTION_NAME,
        field_name="doc_id",
        field_schema="keyword",
    )
    logger.debug("Index payload 'doc_id' assuré.")

    client.create_payload_index(
        collection_name=COLLECTION_NAME,
        field_name="version",
        field_schema="integer",
    )
    logger.debug("Index payload 'version' assuré.")

    client.create_payload_index(
        collection_name=COLLECTION_NAME,
        field_name="reponse_id",
        field_schema="keyword",
    )
    logger.debug("Index payload 'reponse_id' assuré.")


def filtre_anciens(doc_id: str, version_cible: int) -> Filter:
    """Points du document hors version en cours. Used for capture AND deletion to hit the exact same set on retries."""
    return Filter(
        must=[FieldCondition(key="doc_id", match=MatchValue(value=doc_id))],
        must_not=[FieldCondition(key="version", match=MatchValue(value=version_cible))],
    )


def capturer_chunks(doc_id: str, version_cible: int) -> dict[int, str]:
    """``{chunk_index: contenu}`` de la version sortante. Must be called before any delete."""
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


def delete_response_point(reponse_id: str) -> None:
    """Supprime **tous** les points associés à une réponse. By payload filter not point id — one response has one"""
    client.delete(
        collection_name=COLLECTION_NAME,
        points_selector=Filter(
            must=[FieldCondition(key="reponse_id", match=MatchValue(value=str(reponse_id)))]
        ),
    )


if __name__ == "__main__":
    init_collection()
