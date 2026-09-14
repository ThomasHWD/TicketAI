"""La fusion dense + lexical : rattrapage croisé des scores, et porte de rappel.

Tests unitaires (Qdrant mocké) — la variante intégration vit dans `test_search.py`.
"""

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from app.services.search import _rechercher, franchit_le_rappel
from qdrant_client.models import FieldCondition, Filter, HasIdCondition, MatchValue


def point(pid: str, score: float, **payload) -> SimpleNamespace:
    return SimpleNamespace(id=pid, score=score, payload={"contenu": "peu importe", **payload})


def resultats(*points) -> SimpleNamespace:
    return SimpleNamespace(points=list(points))


def chercher(denses, creux, cosinus_rattrapes=(), lexicaux_rattrapes=()):
    """Exécute `_rechercher` avec les quatre interrogations Qdrant simulées.

    Dans l'ordre : dense, lexicale, rattrapage des cosinus manquants, rattrapage
    des scores lexicaux manquants.
    """
    embedding = {"dense": [0.0] * 1024, "sparse": {"indices": [7], "values": [1.0]}}
    with (
        patch("app.services.search.embed_texts", return_value=[embedding]),
        patch("app.services.search.client") as qdrant,
    ):
        qdrant.query_points.side_effect = [
            resultats(*denses),
            resultats(*creux),
            resultats(*cosinus_rattrapes),
            resultats(*lexicaux_rattrapes),
        ]
        return _rechercher("peu importe", Filter(must=[]), top_k=10)


def test_un_point_trouve_par_le_seul_lexical_recoit_son_vrai_cosinus():
    """**La propriété qui fait exister ce chantier.**

    `reciprocal_rank_fusion` ne relève les scores denses que sur la branche dense :
    un point venu du lexical ressortirait à 0.0, et serait donc écarté par tous les
    seuils du système — BM25 n'aurait servi à rien. Une requête Qdrant
    supplémentaire va chercher son cosinus réel.
    """
    resultat = chercher(
        denses=[point("dense-1", 0.90)],
        creux=[point("lexical-1", 3.2)],
        cosinus_rattrapes=[point("lexical-1", 0.67)],
        lexicaux_rattrapes=[point("dense-1", 1.1)],
    )

    lexical = next(r for r in resultat if r["score_sparse"] == 3.2)
    assert lexical["score_cosinus"] == 0.67, "cosinus rattrapé, et non 0.0"


def test_un_point_trouve_par_le_seul_dense_recoit_son_vrai_score_lexical():
    """Le sens miroir, et il compte autant.

    Sans lui, un point hors du top-k lexical est crédité d'un `0.0` alors qu'il
    partage peut-être tous les mots de la requête — il ne peut donc jamais passer
    par la porte lexicale. Mesuré sur le corpus réel : « Combien mesure une poire »
    passait devant « Combien fait une pomme en hauteur ? » pour la requête
    « combien mesure une pomme ? », faute pour la seconde d'avoir été créditée de
    son recouvrement lexical.
    """
    resultat = chercher(
        denses=[point("dense-1", 0.90)],
        creux=[point("lexical-1", 3.2)],
        cosinus_rattrapes=[point("lexical-1", 0.67)],
        lexicaux_rattrapes=[point("dense-1", 4.4)],
    )

    dense = next(r for r in resultat if r["score_cosinus"] == 0.90)
    assert dense["score_sparse"] == 4.4, "score lexical rattrapé, et non 0.0"
    assert dense["score_lexical"] > 0.0, "la porte lexicale doit pouvoir s'ouvrir"


def test_aucune_requete_de_rattrapage_si_le_lexical_n_apporte_rien():
    """Le rattrapage coûte une requête Qdrant : il ne doit pas partir pour rien."""
    embedding = {"dense": [0.0] * 1024, "sparse": {"indices": [7], "values": [1.0]}}
    with (
        patch("app.services.search.embed_texts", return_value=[embedding]),
        patch("app.services.search.client") as qdrant,
    ):
        qdrant.query_points.side_effect = [
            resultats(point("a", 0.9)),
            resultats(point("a", 2.0)),  # déjà vu en dense
        ]
        _rechercher("peu importe", Filter(must=[]), top_k=10)

        assert qdrant.query_points.call_count == 2


class TestPorteDeRappel:
    """La disjonction : le cosinus **ou** le lexical, chacun sur son échelle.

    On ne seuille pas la fusion — aucun score de fusion n'est absolu. Le RRF ne
    dépend que du rang, une fusion par distribution normalise par requête. Les
    signaux bruts, eux, disent quelque chose.
    """

    @staticmethod
    def porte(cosinus, lexical, seuil_lexical=1.0, seuil_cosinus=0.75):
        with patch("app.services.search.settings") as reglages:
            reglages.seuil_lexical_par_terme = seuil_lexical
            return franchit_le_rappel({"score_cosinus": cosinus, "score_lexical": lexical}, seuil_cosinus)

    def test_le_cosinus_seul_suffit(self):
        assert self.porte(cosinus=0.80, lexical=0.0)

    def test_le_lexical_seul_suffit(self):
        """**La raison d'être de BM25.**

        Un sigle, une référence d'article, un nom propre que le modèle
        d'embedding ne connaît pas : cosinus médiocre, recouvrement lexical
        parfait. Sans cette porte, le cas d'usage principal de BM25 resterait
        hors de portée — c'est le défaut du score mélangé qu'elle remplace.
        """
        assert self.porte(cosinus=0.35, lexical=2.4)

    def test_ni_l_un_ni_l_autre_ne_passe_pas(self):
        assert not self.porte(cosinus=0.35, lexical=0.4)

    def test_porte_lexicale_fermee_restitue_le_comportement_d_avant_bm25(self):
        """L'échappatoire : `seuil_lexical_par_terme = 0` referme la porte."""
        assert not self.porte(cosinus=0.35, lexical=10_000, seuil_lexical=0)
        assert self.porte(cosinus=0.80, lexical=0.0, seuil_lexical=0)


def test_le_score_lexical_est_ramene_au_terme():
    """Un score BM25 est une somme sur les termes : brut, il favorise les questions longues.

    Mesuré le 11/09/2026 : bruts 2,17 (2 termes) et 3,42 (3 termes) ; ramenés au
    terme, 1,08 et 1,14 — bien plus comparables.
    """
    embedding = {"dense": [0.0] * 1024, "sparse": {"indices": [7, 8, 9], "values": [1.0, 1.0, 1.0]}}
    with (
        patch("app.services.search.embed_texts", return_value=[embedding]),
        patch("app.services.search.client") as qdrant,
    ):
        qdrant.query_points.side_effect = [
            resultats(point("a", 0.9)),
            resultats(point("a", 3.42)),
            resultats(),
            resultats(),
        ]
        sortie = _rechercher("trois termes ici", Filter(must=[]), top_k=10)

    assert sortie[0]["score_sparse"] == 3.42
    assert sortie[0]["score_lexical"] == pytest.approx(3.42 / 3)


def test_une_requete_sans_aucun_terme_ne_divise_pas_par_zero():
    """Une requête qui ne produit aucun token — et ça arrive.

    La tokenisation exige qu'un token commence par une lettre : « 713 », « 2026 »
    ou « 50 % » sortent donc **vides**. `score_lexical` divise le score brut par
    le nombre de termes ; sans le `max(nb_termes_requete, 1)` de `search.py`, la
    recherche lèverait `ZeroDivisionError` sur une requête purement numérique.
    Mesuré sur le vrai index le 11/09/2026 : « 713 » donne `tokens=[]`.
    """
    embedding = {"dense": [0.0] * 1024, "sparse": {"indices": [], "values": []}}
    with (
        patch("app.services.search.embed_texts", return_value=[embedding]),
        patch("app.services.search.client") as qdrant,
    ):
        qdrant.query_points.side_effect = [
            resultats(point("a", 0.42)),
            resultats(),
            resultats(),
            resultats(),
        ]
        sortie = _rechercher("713", Filter(must=[]), top_k=10)

    assert sortie[0]["score_lexical"] == 0.0
    assert sortie[0]["score_cosinus"] == pytest.approx(0.42)


def _filtre_de_rattrapage(filtre: Filter) -> Filter:
    """Le filtre que `_rechercher` construit pour la 3ᵉ requête (rattrapage)."""
    embedding = {"dense": [0.0] * 1024, "sparse": {"indices": [7], "values": [1.0]}}
    with (
        patch("app.services.search.embed_texts", return_value=[embedding]),
        patch("app.services.search.client") as qdrant,
    ):
        qdrant.query_points.side_effect = [
            resultats(point("dense-1", 0.9)),
            resultats(point("lexical-1", 3.0)),
            resultats(point("lexical-1", 0.5)),
            resultats(point("dense-1", 1.0)),
        ]
        _rechercher("peu importe", filtre, top_k=10)
    return qdrant.query_points.call_args_list[2].kwargs["query_filter"]


@pytest.mark.parametrize(
    "filtre",
    [
        Filter(must=[FieldCondition(key="domaine", match=MatchValue(value="RH"))]),
        # `should` et `min_should` existent aussi, et l'ancienne construction —
        # qui recopiait `must` et `must_not` seulement — les perdait en silence.
        # Un rattrapage plus large que la recherche noterait alors des points
        # que celle-ci avait exclus.
        Filter(should=[FieldCondition(key="domaine", match=MatchValue(value="RH"))]),
        Filter(must_not=[FieldCondition(key="domaine", match=MatchValue(value="RH"))]),
        # Chaque clause accepte une condition **nue** autant qu'une liste. Déplier
        # `filtre.must` levait une ValidationError sur cette forme.
        Filter(must=FieldCondition(key="domaine", match=MatchValue(value="RH"))),
    ],
    ids=["must", "should", "must_not", "condition nue"],
)
def test_le_filtre_de_rattrapage_conserve_les_contraintes_de_la_recherche(filtre):
    """Sans quoi le rattrapage pourrait scorer un point que la recherche excluait.

    On vérifie la **propriété**, pas la forme : le filtre d'origine doit rester
    opposable, quelle que soit la clause utilisée pour l'exprimer. C'est ce qui
    permet de l'imbriquer plutôt que de recopier ses clauses une à une — une
    recopie retombe à chaque fois dans l'oubli d'une clause.
    """
    rattrapage = _filtre_de_rattrapage(filtre)
    assert filtre in (rattrapage.must or []), "le filtre d'origine a été perdu"
    assert any(isinstance(c, HasIdCondition) for c in rattrapage.must), "restriction aux ids manquants perdue"
