import logging
import uuid

from app.config import settings
from qdrant_client import QdrantClient
from qdrant_client.http.exceptions import UnexpectedResponse
from qdrant_client.models import (
    Distance,
    PointIdsList,
    SparseIndexParams,
    SparseVectorParams,
    VectorParams,
)

logger = logging.getLogger(__name__)

client = QdrantClient(host=settings.qdrant_host, port=settings.qdrant_port)

COLLECTION_NAME = "ticketai"


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
                sparse_vectors_config={"sparse": SparseVectorParams(index=SparseIndexParams(on_disk=False))},
            )
            logger.info("Collection '%s' créée.", COLLECTION_NAME)
        except UnexpectedResponse as exc:
            # collection_exists() puis create_collection() n'est pas atomique :
            # avec `uvicorn --workers N`, le lifespan tourne dans chaque process
            # et deux workers peuvent créer la collection en même temps. Le
            # perdant reçoit un 409 et doit converger, pas tuer le démarrage.
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

    # Index payload pour cibler un document et une version — sans eux, les filtres
    # (doc_id, version) de la mise à jour dégénèrent en scan complet de la collection.
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


def delete_response_point(reponse_id: str) -> None:
    """Supprime de Qdrant le point associé à une réponse.

    Réutilise l'ID déterministe employé à l'upsert dans le feedback_job
    (uuid5 dérivé de l'id de la réponse), afin de retrouver le même point.
    """
    point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, str(reponse_id)))
    client.delete(
        collection_name=COLLECTION_NAME,
        points_selector=PointIdsList(points=[point_id]),
    )


if __name__ == "__main__":
    init_collection()
