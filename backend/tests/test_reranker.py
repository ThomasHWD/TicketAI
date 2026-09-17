from unittest.mock import MagicMock, patch


def test_rerank_chunks_vides():
    from app.services.reranker import rerank

    # Si la liste est vide, pas d'appel API, retour immédiat
    assert rerank("question", []) == []


def test_rerank_top_k_respecte():
    from app.services.reranker import rerank

    chunks = [{"contenu": "texte A"}, {"contenu": "texte B"}]

    with patch("app.services.reranker.requests.post") as mock_post:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"results": [{"index": 0, "relevance_score": 0.95}]}
        mock_post.return_value = mock_response

        res = rerank("ma question", chunks, top_k=1)
        assert len(res) == 1
        assert res[0]["contenu"] == "texte A"


def test_rerank_trie_par_score_decroissant():
    from app.services.reranker import rerank

    chunks = [{"contenu": "Moins bon"}, {"contenu": "Le meilleur"}]

    with patch("app.services.reranker.requests.post") as mock_post:
        mock_response = MagicMock()
        mock_response.status_code = 200
        # Albert renvoie trié par score, par exemple l'index 1 en premier
        mock_response.json.return_value = {
            "results": [
                {"index": 1, "relevance_score": 0.99},
                {"index": 0, "relevance_score": 0.42},
            ]
        }
        mock_post.return_value = mock_response

        res = rerank("ma question", chunks, top_k=2)
        assert res[0]["contenu"] == "Le meilleur"
        assert res[1]["contenu"] == "Moins bon"


def test_rerank_contient_rerank_score():
    from app.services.reranker import rerank

    chunks = [{"contenu": "texte d'exemple"}]

    with patch("app.services.reranker.requests.post") as mock_post:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"results": [{"index": 0, "relevance_score": 0.88}]}
        mock_post.return_value = mock_response

        res = rerank("ma question", chunks)
        assert "rerank_score" in res[0]
        assert res[0]["rerank_score"] == 0.88


def test_rerank_envoie_le_texte_indexe_quand_il_existe():
    """Le cross-encoder juge le chunk avec son locateur, comme la recherche l'a trouvé.

    Sans ça, un passage référentiellement opaque (« les intéressés en sont
    exclus ») remonté grâce à son contexte serait reclassé dernier et n'atteindrait
    jamais la génération. Repli sur `contenu` : `unites_pertinentes` bâtit ses
    dicts à la main et n'a pas cette clé.
    """
    from app.services.reranker import rerank

    chunks = [
        {"contenu": "brut A", "contenu_indexe": "locateur\n\nbrut A"},
        {"contenu": "brut B"},
    ]

    with patch("app.services.reranker.requests.post") as mock_post:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"results": [{"index": 0, "relevance_score": 0.9}]}
        mock_post.return_value = mock_response

        res = rerank("ma question", chunks, top_k=1)

    assert mock_post.call_args.kwargs["json"]["documents"] == ["locateur\n\nbrut A", "brut B"]
    # Le chunk rendu reste celui d'origine : c'est lui qui part en base (ReponseChunk).
    assert res[0]["contenu"] == "brut A"
