"""Tests du garde du cache canonique.

Propriété centrale : toute réponse autre que "OUI" explicite → False.
Erreur LLM, timeout, réponse ambiguë → False (conservateur par construction).
"""

from unittest.mock import patch

import pytest


@pytest.mark.parametrize("a, b", [
    ("Combien de jours de congé ?", "Combien de jours de congé ?"),
    ("Combien de JOURS de congé ?", "combien de jours de congé ?"),
    ("Combien  de jours de congé ?", "Combien de jours de congé ?"),
])
def test_repetition_exacte_approuve_sans_llm(a, b):
    from app.services.garde_cache import approuver

    with patch("app.services.garde_cache.chat") as mock_chat:
        assert approuver(a, b) is True
        mock_chat.assert_not_called()


def test_llm_oui_approuve():
    from app.services.garde_cache import approuver

    with patch("app.services.garde_cache.chat", return_value="OUI"):
        assert approuver("Puis-je télétravailler ?", "Puis-je faire du télétravail ?") is True


@pytest.mark.parametrize("verdict", ["NON", "non", "Peut-être", "", "OUI mais attention"])
def test_llm_non_refuse(verdict):
    from app.services.garde_cache import approuver

    with patch("app.services.garde_cache.chat", return_value=verdict):
        assert approuver("Puis-je télétravailler 5 jours ?", "Puis-je télétravailler 3 jours ?") is False


def test_llm_exception_refuse():
    from app.services.garde_cache import approuver

    with patch("app.services.garde_cache.chat", side_effect=Exception("timeout")):
        assert approuver("Question A", "Question B") is False
