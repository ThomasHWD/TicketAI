from unittest.mock import patch, MagicMock
import numpy as np


def make_chunks(n=3):
    return [
        {
            "contenu": f"texte {i}",
            "source": "doc.pdf",
            "score_cosinus": 0.5,
            "score_rrf": 0.01,
            "doc_id": "1",
            "domaine": "IT",
            "chunk_index": i,
        }
        for i in range(n)
    ]


def test_rerank_chunks_vides():
    from app.services.reranker import rerank

    with patch("app.services.reranker.get_reranker") as mock:
        mock.return_value.predict.return_value = []
        results = rerank("question", [], top_k=3)
        assert results == []


def test_rerank_top_k_respecte():
    from app.services.reranker import rerank

    with patch("app.services.reranker.get_reranker") as mock:
        mock.return_value.predict.return_value = [0.9, 0.5, 0.3]
        results = rerank("question test", make_chunks(3), top_k=2)
        assert len(results) <= 2


def test_rerank_trie_par_score_decroissant():
    from app.services.reranker import rerank

    with patch("app.services.reranker.get_reranker") as mock:
        mock.return_value.predict.return_value = [0.3, 0.9]
        chunks = make_chunks(2)
        results = rerank("question", chunks, top_k=2)
        assert results[0]["rerank_score"] >= results[1]["rerank_score"]


def test_rerank_contient_rerank_score():
    from app.services.reranker import rerank

    with patch("app.services.reranker.get_reranker") as mock:
        mock.return_value.predict.return_value = [0.85]
        results = rerank("deep learning", make_chunks(1), top_k=1)
        assert "rerank_score" in results[0]
        assert isinstance(results[0]["rerank_score"], float)
