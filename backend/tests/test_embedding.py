from unittest.mock import MagicMock, patch


def test_embed_retourne_bonne_structure():
    # 🎯 On patch directement l'instance 'client' du module
    with patch("app.services.embedding.client") as mock_client:
        # On simule la réponse de l'API Albert
        mock_item = MagicMock()
        mock_item.embedding = [0.1, 0.2, 0.3]
        mock_response = MagicMock()
        mock_response.data = [mock_item]
        mock_client.embeddings.create.return_value = mock_response

        # On importe le service APRES avoir posé le patch
        from app.services.embedding import embed_texts

        res = embed_texts(["un texte à vectoriser"])

        assert len(res) == 1
        assert "dense" in res[0]
        assert "sparse" in res[0]
        assert res[0]["dense"] == [0.1, 0.2, 0.3]
        assert res[0]["sparse"] == {"indices": [], "values": []}


def test_embed_plusieurs_textes():
    with patch("app.services.embedding.client") as mock_client:
        mock_item_1 = MagicMock()
        mock_item_1.embedding = [0.1, 0.2]
        mock_item_2 = MagicMock()
        mock_item_2.embedding = [0.4, 0.5]

        mock_response = MagicMock()
        mock_response.data = [mock_item_1, mock_item_2]
        mock_client.embeddings.create.return_value = mock_response

        from app.services.embedding import embed_texts

        res = embed_texts(["texte 1", "texte 2"])

        assert len(res) == 2
        assert res[0]["dense"] == [0.1, 0.2]
        assert res[1]["dense"] == [0.4, 0.5]
