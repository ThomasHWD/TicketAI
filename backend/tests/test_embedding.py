from app.services.embedding import embed_texts


def test_embed_retourne_bonne_dimension():
    results = embed_texts(["test"])
    assert len(results) == 1
    assert len(results[0]["dense"]) == 1024
    assert len(results[0]["sparse"]["indices"]) > 0


def test_embed_deterministe():
    r1 = embed_texts(["même texte"])
    r2 = embed_texts(["même texte"])
    assert r1[0]["dense"] == r2[0]["dense"]
