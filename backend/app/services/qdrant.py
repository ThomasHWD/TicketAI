from qdrant_client import QdrantClient
from qdrant_client.models import (
    VectorParams, Distance,
    SparseVectorParams, SparseIndexParams
)
from app.config import settings

client = QdrantClient(
    host=settings.qdrant_host,
    port=settings.qdrant_port
)

COLLECTION_NAME = "ticketai"

def init_collection():
    if client.collection_exists(collection_name=COLLECTION_NAME):
        print(f"Collection '{COLLECTION_NAME}' existe déjà.")
        return

    client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config={
            "dense": VectorParams(
                size=1024,        # BGE-M3
                distance=Distance.COSINE
            )
        },
        sparse_vectors_config={
            "sparse": SparseVectorParams(
                index=SparseIndexParams(on_disk=False)
            )
        }
    )
    print(f"Collection '{COLLECTION_NAME}' créée.")

if __name__ == "__main__":
    init_collection()
