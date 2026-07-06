# tests/test_search.py
import random
from unittest.mock import patch

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


def fake_embeddings(n: int = 1) -> list[dict]:
    """Embeddings factices — évite de télécharger/charger le vrai BGE-M3 (2,3 Go)."""
    return [
        {
            "dense": [random.uniform(-1, 1) for _ in range(1024)],
            "sparse": {"indices": [1, 42, 1024], "values": [0.5, 0.3, 0.2]},
        }
        for _ in range(n)
    ]


def test_search_retourne_bonne_structure():
    from app.services.search import search_hybrid

    with patch("app.services.search.embed_texts", return_value=fake_embeddings(1)):
        results = search_hybrid("test", "IT", top_k=3)

    assert isinstance(results, list)
    for r in results:
        assert "score_cosinus" in r
        assert "score_rrf" in r
        assert "contenu" in r
        assert "source" in r


def test_search_filtre_par_domaine():
    """Le filtre domaine doit être transmis à Qdrant (aucune fuite inter-domaines)."""
    from app.services import search as search_module

    with patch("app.services.search.embed_texts", return_value=fake_embeddings(1)), \
         patch.object(search_module, "client") as mock_client:
        mock_client.query_points.return_value.points = []
        search_module.search_hybrid("test", "RH", top_k=3)

        assert mock_client.query_points.call_count == 2
        for call in mock_client.query_points.call_args_list:
            query_filter = call.kwargs.get("query_filter")
            assert query_filter is not None, "query_filter manquant"
            assert query_filter.must[0].key == "domaine"
            assert query_filter.must[0].match.value == "RH"
