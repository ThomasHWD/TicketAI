from unittest.mock import MagicMock, patch


def item(index: int, embedding: list[float]) -> MagicMock:
    """Une entrée de `response.data` telle que la renvoie l'API Albert.

    `index` est la position du texte dans le lot envoyé. C'est lui qui fait foi,
    et non l'ordre d'itération : s'y fier évite d'apparier le vecteur creux d'un
    texte au vecteur dense d'un autre.
    """
    faux = MagicMock()
    faux.index = index
    faux.embedding = embedding
    return faux


def reponse_albert(*items) -> MagicMock:
    faux = MagicMock()
    faux.data = list(items)
    return faux


def test_embed_retourne_bonne_structure():
    with patch("app.services.embedding.client") as mock_client:
        mock_client.embeddings.create.return_value = reponse_albert(item(0, [0.1, 0.2, 0.3]))

        from app.services.embedding import embed_texts

        res = embed_texts(["un texte à vectoriser"])

        assert len(res) == 1
        assert res[0]["dense"] == [0.1, 0.2, 0.3]
        # Le vecteur creux n'est plus vide : BM25 est calculé localement.
        assert res[0]["sparse"]["indices"]
        assert len(res[0]["sparse"]["indices"]) == len(res[0]["sparse"]["values"])


def test_embed_plusieurs_textes():
    with patch("app.services.embedding.client") as mock_client:
        mock_client.embeddings.create.return_value = reponse_albert(item(0, [0.1, 0.2]), item(1, [0.4, 0.5]))

        from app.services.embedding import embed_texts

        res = embed_texts(["texte 1", "texte 2"])

        assert len(res) == 2
        assert res[0]["dense"] == [0.1, 0.2]
        assert res[1]["dense"] == [0.4, 0.5]


def test_apparie_par_index_et_non_par_ordre_de_retour():
    """`response.data` n'est pas garanti ordonné — chaque entrée porte son `index`.

    Si l'appariement suivait l'ordre d'itération, le vecteur creux de « congés »
    se retrouverait collé au vecteur dense de « télétravail ». Panne silencieuse :
    aucune erreur, juste des résultats faux.
    """
    from app.services.bm25 import encoder
    from app.services.embedding import embed_texts

    with patch("app.services.embedding.client") as mock_client:
        # Albert renvoie les deux entrées dans l'ordre inverse.
        mock_client.embeddings.create.return_value = reponse_albert(item(1, [0.9]), item(0, [0.1]))

        res = embed_texts(["congés", "télétravail"])

    assert res[0]["dense"] == [0.1]
    assert res[0]["sparse"] == encoder("congés")
    assert res[1]["dense"] == [0.9]
    assert res[1]["sparse"] == encoder("télétravail")


def test_is_query_change_la_ponderation():
    """Une requête ne porte pas de pondération TF, un document si."""
    from app.services.embedding import embed_texts

    with patch("app.services.embedding.client") as mock_client:
        mock_client.embeddings.create.return_value = reponse_albert(item(0, [0.1]))
        requete = embed_texts(["congés payés"], is_query=True)[0]["sparse"]

        mock_client.embeddings.create.return_value = reponse_albert(item(0, [0.1]))
        document = embed_texts(["congés payés"], is_query=False)[0]["sparse"]

    assert requete["values"] == [1.0, 1.0]
    assert document["values"] != requete["values"]
