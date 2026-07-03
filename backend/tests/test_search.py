# tests/test_search.py
def test_search_retourne_bonne_structure():
    from app.services.search import search_hybrid

    results = search_hybrid("test", "IT", top_k=3)
    assert isinstance(results, list)
    for r in results:
        assert "score_cosinus" in r
        assert "score_rrf" in r
        assert "contenu" in r
        assert "source" in r
