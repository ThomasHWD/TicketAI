from unittest.mock import patch
import numpy as np


def test_embed_retourne_bonne_structure():
    from app.services.embedding import embed_texts

    with patch("app.services.embedding.get_model") as mock:
        fake_output = {
            "dense_vecs": [np.random.rand(1024).astype(np.float32)],
            "lexical_weights": [{"1": 0.5, "2": 0.3}],
        }
        mock.return_value.encode.return_value = fake_output
        results = embed_texts(["test"])
        assert len(results) == 1
        assert len(results[0]["dense"]) == 1024
        assert len(results[0]["sparse"]["indices"]) > 0


def test_embed_plusieurs_textes():
    from app.services.embedding import embed_texts

    with patch("app.services.embedding.get_model") as mock:
        fake_output = {
            "dense_vecs": [np.random.rand(1024).astype(np.float32) for _ in range(3)],
            "lexical_weights": [{"1": 0.5} for _ in range(3)],
        }
        mock.return_value.encode.return_value = fake_output
        results = embed_texts(["a", "b", "c"])
        assert len(results) == 3
