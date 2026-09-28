"""Lecture de la reformulation d'un suivi : une sortie douteuse n'est jamais indexée."""

import pytest
from app.services.reformulation import LONGUEUR_MAX, lire_reformulation


@pytest.mark.parametrize(
    "brut, attendu",
    [
        ("Combien de jours de congés pour un CDD ?", "Combien de jours de congés pour un CDD ?"),
        ("3. « Combien de jours de congés pour un CDD ? »", "Combien de jours de congés pour un CDD ?"),
        ("Voici la question :\nCombien de jours pour un CDD ?", None),  # bavardage : on ne devine pas
        ("", None),
        ("x" * (LONGUEUR_MAX + 1), None),  # a répondu au lieu de reformuler
    ],
)
def test_lire_reformulation(brut, attendu):
    assert lire_reformulation(brut) == attendu
