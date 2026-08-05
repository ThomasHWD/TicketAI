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

client = QdrantClient(host=settings.qdrant_host, port=settings.qdrant_port)

COLLECTION_NAME = "ticketai"


def init_collection():
    if client.collection_exists(collection_name=COLLECTION_NAME):
        print(f"Collection '{COLLECTION_NAME}' existe déjà.")
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
            print(f"Collection '{COLLECTION_NAME}' créée.")
        except UnexpectedResponse as exc:
            # collection_exists() puis create_collection() n'est pas atomique :
            # avec `uvicorn --workers N`, le lifespan tourne dans chaque process
            # et deux workers peuvent créer la collection en même temps. Le
            # perdant reçoit un 409 et doit converger, pas tuer le démarrage.
            if exc.status_code != 409:
                raise
            print(f"Collection '{COLLECTION_NAME}' créée en parallèle par un autre worker.")

    # Index payload pour le filtrage par domaine (idempotent)
    client.create_payload_index(
        collection_name=COLLECTION_NAME,
        field_name="domaine",
        field_schema="keyword",
    )
    print("Index payload 'domaine' assuré.")

    # Index payload pour la détection de doublons par hash (idempotent)
    client.create_payload_index(
        collection_name=COLLECTION_NAME,
        field_name="content_hash",
        field_schema="keyword",
    )
    print("Index payload 'content_hash' assuré.")


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
