# tests/test_search.py
import pytest
from qdrant_client import QdrantClient
from qdrant_client.http import models


@pytest.fixture(scope="session", autouse=True)
def setup_test_qdrant():
    client = QdrantClient(host="localhost", port=6333)

    # Si la collection n'existe pas, on la crée avec la double configuration hybride
    if not client.collection_exists("ticketai"):
        client.create_collection(
            collection_name="ticketai",

            # 1. Vecteur Dense (Sémantique - Ex: BGE-M3 dense à 1024 dim)
            vectors_config={
                "dense": models.VectorParams(
                    size=1024,
                    distance=models.Distance.COSINE
                )
            },

            # 2. Vecteur Sparse (Mots-clés - Indispensable pour la recherche hybride)
            sparse_vectors_config={
                "sparse": models.SparseVectorParams()
            }
        )
    yield


def test_search_retourne_bonne_structure():
    from app.services.search import search_hybrid

    results = search_hybrid("test", "IT", top_k=3)
    assert isinstance(results, list)
    for r in results:
        assert "score_cosinus" in r
        assert "score_rrf" in r
        assert "contenu" in r
        assert "source" in r
