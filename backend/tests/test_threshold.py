"""Sanité des deux planchers de candidature du cache.

`SEUIL_COSINUS` a disparu du pipeline : mesuré non informatif (AUC 0.000), il ne
gouverne plus aucune branche. Ce qui décide du service sans revue humaine, c'est
désormais le garde (`app/services/garde_cache.py`). Voir
`Docs/garde-cache-canonique.md`.
"""

from app.workers.question import SEUIL_CANDIDAT_CANONIQUE, SEUIL_SUGGESTION


def test_les_planchers_sont_dans_une_plage_plausible():
    assert 0.40 <= SEUIL_CANDIDAT_CANONIQUE <= 0.95
    assert 0.40 <= SEUIL_SUGGESTION <= 0.95


def test_les_planchers_sont_des_flottants():
    assert isinstance(SEUIL_CANDIDAT_CANONIQUE, float)
    assert isinstance(SEUIL_SUGGESTION, float)


def test_le_plancher_canonique_est_le_plus_bas_des_deux():
    """L'ordre porte la conception, et l'inverser retournerait le correctif.

    Le plancher canonique est bas parce que ces candidats passent devant les juges
    avant d'être servis ; celui de SUGGESTION reste haut parce qu'aucun juge ne
    filtre cette branche. Les intervertir noierait le validateur sous des réponses
    génériques hors sujet, et priverait le garde des reformulations légitimes
    (mesurées entre 0.71 et 0.79) qu'il est justement là pour rattraper.
    """
    assert SEUIL_CANDIDAT_CANONIQUE <= SEUIL_SUGGESTION
