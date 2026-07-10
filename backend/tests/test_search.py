import json
import os
import random
from unittest.mock import MagicMock, patch

import pytest
from qdrant_client import QdrantClient
from qdrant_client.http import models

# 🎯 Chemin dynamique vers ton fichier de test
GOLDEN_SET_PATH = os.path.join(os.path.dirname(__file__), "golden_set.json")

if os.path.exists(GOLDEN_SET_PATH):
    with open(GOLDEN_SET_PATH, "r", encoding="utf-8") as f:
        golden_cases = json.load(f)
else:
    golden_cases = []


@pytest.fixture(scope="session", autouse=True)
def setup_test_qdrant():
    client = QdrantClient(host="localhost", port=6333)

    if not client.collection_exists("ticketai"):
        client.create_collection(
            collection_name="ticketai",
            vectors_config={
                "dense": models.VectorParams(size=1024, distance=models.Distance.COSINE)
            },
            sparse_vectors_config={"sparse": models.SparseVectorParams()},
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

    with patch(
        "app.services.search.embed_texts", return_value=fake_embeddings(1)
    ), patch.object(search_module, "client") as mock_client:
        mock_client.query_points.return_value.points = []
        search_module.search_hybrid("test", "RH", top_k=3)

        assert mock_client.query_points.call_count == 2
        for call in mock_client.query_points.call_args_list:
            query_filter = call.kwargs.get("query_filter")
            assert query_filter is not None, "query_filter manquant"
            assert query_filter.must[0].key == "domaine"
            assert query_filter.must[0].match.value == "RH"


# 🚀 NOUVEAU : Validation automatique via ton Golden Dataset
@pytest.mark.parametrize("case", golden_cases)
def test_rag_precision_golden_set(case):
    """Vérifie que search_hybrid renvoie le bon fichier pour chaque question du Golden Set."""
    from app.services import search as search_module

    query = case["query"]
    expected_file = case["expected_file"]

    # Détection dynamique du domaine requis par ta fonction search_hybrid
    # Si le fichier attendu contient "Teletravail" ou "RGPD", on cherche en RH, sinon en IT
    domaine = "IT"
    if expected_file and any(
        k in expected_file for k in ["Teletravail", "RGPD", "Salarie"]
    ):
        domaine = "RH"

    with patch(
        "app.services.search.embed_texts", return_value=fake_embeddings(1)
    ), patch.object(search_module, "client") as mock_client:

        # On prépare la fausse réponse de Qdrant (query_points)
        mock_response = MagicMock()
        if expected_file:
            mock_point = MagicMock()
            mock_point.id = random.randint(1, 100)
            mock_point.score = 0.88
            mock_point.payload = {
                "contenu": case.get("ground_truth", "Contenu simulé de la fiche"),
                "source": expected_file,
                "domaine": domaine,
            }
            mock_response.points = [mock_point]
        else:
            # Cas du hors-sujet : Qdrant ne renvoie aucun point pertinent
            mock_response.points = []

        mock_client.query_points.return_value = mock_response

        # Appel à ton vrai moteur de recherche hybride
        results = search_module.search_hybrid(query, domaine, top_k=3)

        # Assertions
        if expected_file:
            assert (
                len(results) > 0
            ), f"Le moteur n'a rien renvoyé pour la requête : '{query}'"
            assert (
                results[0]["source"] == expected_file
            ), f"Mauvais document trouvé pour '{query}'"
        else:
            # Si c'est hors-sujet, la liste doit être vide (ou filtrée par ton seuil/threshold)
            assert (
                len(results) == 0
            ), f"Le moteur aurait dû ignorer la requête hors-sujet : '{query}'"
