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


def test_suivi_ne_court_circuite_pas():
    """En mode suivi, `question_posee` est le fil entier. Court-circuiter sur une
    égalité typographique reviendrait à servir une réponse canonique en ayant
    jeté le contexte qui la rend sûre : le juge doit être appelé.
    """
    from app.services.garde_cache import approuver

    with patch("app.services.garde_cache.chat", return_value="OUI") as mock_chat:
        assert approuver("Combien de jours de congé ?", "Combien de jours de congé ?",
                         est_suivi=True) is True
        mock_chat.assert_called_once()


def test_suivi_utilise_le_prompt_dedie():
    """Le juge doit apprendre que seule la dernière ligne du fil est la demande.
    Sans ce prompt, il compare deux questions empilées à une question unique et
    refuse par artefact de format.
    """
    from app.services.garde_cache import _PROMPT_SYSTEME, _PROMPT_SYSTEME_SUIVI, approuver

    with patch("app.services.garde_cache.chat", return_value="OUI") as mock_chat:
        approuver("Q1\nQ2", "Q3", est_suivi=True)
        assert mock_chat.call_args.args[0][0]["content"] == _PROMPT_SYSTEME_SUIVI

    with patch("app.services.garde_cache.chat", return_value="OUI") as mock_chat:
        approuver("Q1", "Q3")
        assert mock_chat.call_args.args[0][0]["content"] == _PROMPT_SYSTEME


def test_statuer_distingue_court_circuit_et_jugement():
    """Le journal d'audit repose sur cette distinction : un OUI sans appel LLM
    et un OUI du juge servent tous deux la réponse, mais ne valent pas preuve
    de la même chose.
    """
    from app.services.garde_cache import statuer

    with patch("app.services.garde_cache.chat") as mock_chat:
        d = statuer("Combien de jours ?", "combien de jours ?")
        assert (d.verdict, d.court_circuit, d.modele) == (True, True, None)
        mock_chat.assert_not_called()

    with patch("app.services.garde_cache.chat", return_value="OUI"):
        d = statuer("Puis-je télétravailler ?", "Puis-je faire du télétravail ?")
        assert (d.verdict, d.court_circuit) == (True, False)
        assert d.modele  # le modèle qui a rendu le verdict doit être tracé

    with patch("app.services.garde_cache.chat", side_effect=Exception("timeout")):
        d = statuer("Question A", "Question B")
        assert d.verdict is False
        assert d.erreur  # refus faute d'Albert : ce n'est pas un jugement
