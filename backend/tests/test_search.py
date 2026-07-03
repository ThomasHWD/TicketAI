# tests/test_search.py

import pytest
from qdrant_client import QdrantClient
from qdrant_client.http import models


@pytest.fixture(scope="session", autouse=True)
def setup_test_qdrant():
    # On se connecte au Qdrant local (celui de ton PC ou de la CI)
    client = QdrantClient(host="localhost", port=6333)

    # Si la collection n'existe pas, on la crée proprement pour le test
    if not client.collection_exists("ticketai"):
        client.create_collection(
            collection_name="ticketai",
            # Configure les vecteurs denses (ex: taille 1024 pour BGE-M3)
            vectors_config=models.VectorParams(
                size=1024,  # ⚠️ Ajuste cette taille selon la dimension de tes embeddings BGE-M3
                distance=models.Distance.COSINE,
            ),
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
