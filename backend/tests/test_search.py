import json
import os
import random
from unittest.mock import MagicMock, patch

import pytest

# Ce module exige un vrai Qdrant (fixture setup_test_qdrant ci-dessous) → catégorie
# intégration : exécuté sur GitHub Actions, auto-skippé en local sans infra.
pytestmark = pytest.mark.integration

# 🎯 Chemin dynamique vers ton fichier de test
GOLDEN_SET_PATH = os.path.join(os.path.dirname(__file__), "golden_set.json")

if os.path.exists(GOLDEN_SET_PATH):
    with open(GOLDEN_SET_PATH, "r", encoding="utf-8") as f:
        golden_cases = json.load(f)
else:
    golden_cases = []


@pytest.fixture(scope="session", autouse=True)
def setup_test_qdrant():
    """Garantit l'existence de la collection de test, via le code de production.

    Cette fixture construisait sa propre collection à la main, sur `localhost:6333`
    (la prod) et sous le nom `"ticketai"` (celui de la prod). Elle a donc pu créer
    la collection de production avec une configuration sparse *divergente* — sans
    `modifier=Modifier.IDF` — que `init_collection` n'aurait jamais corrigée
    ensuite, puisqu'il se contente de constater qu'elle existe.

    Deux changements, et c'est tout ce qui compte ici :
    - le nom vient de `settings.qdrant_collection`, que conftest a suffixé `_test` ;
    - la création passe par `init_collection()`, donc par la configuration réelle.
      Une divergence est désormais impossible par construction : il n'y a plus
      qu'une seule définition de la collection dans le dépôt.
    """
    from app.services.qdrant import COLLECTION_NAME, client, init_collection

    # Ceinture et bretelles : si le forçage de conftest n'a pas eu lieu (module
    # importé autrement, variable écrasée), on refuse plutôt que d'écrire sur la
    # collection de production.
    assert "test" in COLLECTION_NAME.lower(), (
        f"Collection ciblée « {COLLECTION_NAME} » : refus d'exécuter les tests "
        "d'intégration hors d'une collection de test."
    )

    try:
        init_collection()
    except Exception as exc:  # Qdrant injoignable → on saute, on ne casse pas
        pytest.skip(f"Qdrant injoignable ({exc!r}) — tests d'intégration ignorés")

    yield

    # La collection est jetable : on la retire pour ne pas laisser de résidu sur
    # l'instance visée (qui peut être celle de la prod, cf. conftest).
    try:
        client.delete_collection(collection_name=COLLECTION_NAME)
    except Exception:
        pass


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

    with (
        patch("app.services.search.embed_texts", return_value=fake_embeddings(1)),
        patch.object(search_module, "client") as mock_client,
    ):
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
    domaine = case.get("domaine", "IT")

    with (
        patch("app.services.search.embed_texts", return_value=fake_embeddings(1)),
        patch.object(search_module, "client") as mock_client,
    ):
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
            assert len(results) > 0, f"Le moteur n'a rien renvoyé pour la requête : '{query}'"
            assert results[0]["source"] == expected_file, f"Mauvais document trouvé pour '{query}'"
        else:
            # Si c'est hors-sujet, la liste doit être vide (ou filtrée par ton seuil/threshold)
            assert len(results) == 0, f"Le moteur aurait dû ignorer la requête hors-sujet : '{query}'"
