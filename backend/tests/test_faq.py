"""FAQ — recherche sémantique dans les réponses canoniques.

Trois propriétés valent d'être tenues par un test : ce qui est exposé (seules les
canoniques servies), ce que ça coûte (un embedding par recherche, pas un par
domaine), et le dédoublonnage des formulations multiples.
"""

from unittest.mock import patch

import pytest
from app.services.faq import rechercher_faq

from .helpers_reponses import API, seed_ticket_reponse

SEUIL = 0.75  # settings.faq_seuil_pertinence
SEUIL_INCERTAIN = 0.55  # settings.faq_seuil_incertain


def point(reponse_id, score, question="Question indexée ?"):
    """Un chunk tel que le renvoie `rechercher_points_reponses`."""
    return {
        "reponse_id": str(reponse_id),
        "score_cosinus": score,
        "question_indexee": question,
        "contenu": "peu importe",
        "domaine": "IT",
    }


@pytest.mark.integration
@pytest.mark.parametrize(
    "attribut",
    ["non_canonique", "obsolete", "a_relire", "faq_invisible"],
    ids=[
        "réponse non canonique",
        "réponse canonique obsolète",
        "réponse canonique signalée à relire",
        "réponse canonique non exposée",
    ],
)
def test_seules_les_canoniques_servies_sortent(db_session, attribut):
    """La propriété de sûreté : un score parfait ne suffit pas à être exposé.

    Chaque cas n'écarte qu'un drapeau, tous les autres étant passants — sans quoi
    le test passerait pour la mauvaise raison.

    `a_relire` : cette page n'a **aucun relecteur**. Y montrer une réponse qu'un
    juge soupçonne contredite serait exactement la servir sans revue, ce que la
    FAQ ne fait jamais. Le pipeline, lui, continue de la proposer — en SUGGESTION,
    sous les yeux d'un humain.
    """
    _, reponse = seed_ticket_reponse(
        db_session,
        statut="VALIDÉE",
        canonique=(attribut != "non_canonique"),
        nb_validations=3,
        faq_visible=(attribut != "faq_invisible"),
    )
    if attribut in ("obsolete", "a_relire"):
        setattr(reponse, attribut, True)
        db_session.commit()

    with patch(
        "app.services.faq.rechercher_points_reponses",
        return_value=[point(reponse.id, 0.99)],
    ):
        rangs = rechercher_faq(db_session, "peu importe", 5)

    # Ni servie, ni même proposée comme piste incertaine.
    assert rangs == {"resultats": [], "incertains": []}


@pytest.mark.integration
@pytest.mark.parametrize(
    ("canonique", "a_relire"),
    [(True, False), (True, True), (False, False), (False, True)],
)
def test_le_filtre_sql_dit_la_meme_chose_que_le_predicat_python(db_session, canonique, a_relire):
    """Le filtre SQL de la FAQ et `peut_servir_sans_revue` ne doivent pas diverger.

    Deux endroits énoncent « cette réponse a-t-elle le droit d'être vue sans
    relecteur » : un prédicat Python dans le pipeline, une clause SQL ici. Une
    divergence ne lèverait rien — elle rouvrirait juste, d'un côté, la porte que
    l'autre a fermée. Même risque que `obsolete`, déjà filtré des deux côtés.

    Les drapeaux hors du prédicat (`obsolete`, `faq_visible`) sont tenus passants :
    c'est la paire `(canonique, a_relire)` qu'on compare, rien d'autre.
    """
    from app.services.question_pipeline import peut_servir_sans_revue

    _, reponse = seed_ticket_reponse(
        db_session, statut="VALIDÉE", canonique=canonique, nb_validations=3, faq_visible=True
    )
    reponse.a_relire = a_relire
    db_session.commit()

    with patch(
        "app.services.faq.rechercher_points_reponses",
        return_value=[point(reponse.id, 0.99)],
    ):
        expose = bool(rechercher_faq(db_session, "peu importe", 5)["resultats"])

    assert expose is peut_servir_sans_revue(reponse)


@pytest.mark.integration
def test_un_seul_embedding_et_aucun_filtre_de_domaine(db_session):
    """Propriété de coût : une recherche = **un** appel Albert, pas un par domaine.

    Garde contre la réintroduction d'une boucle « un `search_hybrid` par domaine »,
    qui multiplierait la consommation du quota par le nombre de domaines.
    """
    embedding = {"dense": [0.0] * 1024, "sparse": {"indices": [1], "values": [0.5]}}

    with (
        patch("app.services.search.embed_texts", return_value=[embedding]) as embed,
        patch("app.services.search.client") as qdrant,
    ):
        qdrant.query_points.return_value.points = []
        rechercher_faq(db_session, "congés et VPN", 5)

    assert embed.call_count == 1

    filtres = [appel.kwargs["query_filter"] for appel in qdrant.query_points.call_args_list]
    assert filtres, "aucune interrogation Qdrant"
    for filtre in filtres:
        # Tous domaines confondus : rien ne doit restreindre par `domaine`…
        assert not filtre.must
        # …et seuls les points de réponse sont éligibles.
        assert filtre.must_not[0].is_empty.key == "reponse_id"


@pytest.mark.integration
def test_dedoublonne_les_formulations_et_garde_la_gagnante(db_session):
    """Deux points (deux formulations) d'une même réponse → un résultat, la meilleure question."""
    _, reponse = seed_ticket_reponse(db_session, statut="VALIDÉE", canonique=True, nb_validations=3, faq_visible=True)

    with patch(
        "app.services.faq.rechercher_points_reponses",
        return_value=[
            point(reponse.id, SEUIL + 0.01, "Formulation faible ?"),
            point(reponse.id, SEUIL + 0.10, "Formulation gagnante ?"),
        ],
    ):
        resultats = rechercher_faq(db_session, "peu importe", 5)["resultats"]

    assert len(resultats) == 1
    assert resultats[0]["question"] == "Formulation gagnante ?"
    assert "score" not in resultats[0]  # le cosinus ordonne, il ne sort pas de l'API


# Le second rang est une piste, jamais une réponse : il ne doit apparaître que
# lorsque rien n'a franchi le seuil, et disparaître dès qu'une réponse sûre existe.
@pytest.mark.integration
@pytest.mark.parametrize(
    ("score", "attendu"),
    [
        (SEUIL + 0.01, "resultats"),
        (SEUIL - 0.01, "incertains"),
        (SEUIL_INCERTAIN - 0.01, None),
    ],
    ids=["au-dessus du seuil", "entre les deux seuils", "sous le plancher"],
)
def test_rang_selon_le_score(db_session, score, attendu):
    _, reponse = seed_ticket_reponse(db_session, statut="VALIDÉE", canonique=True, nb_validations=3, faq_visible=True)

    with patch(
        "app.services.faq.rechercher_points_reponses",
        return_value=[point(reponse.id, score)],
    ):
        rangs = rechercher_faq(db_session, "peu importe", 5)

    for rang in ("resultats", "incertains"):
        attendus = 1 if rang == attendu else 0
        assert len(rangs[rang]) == attendus, f"{rang} à {score}"


@pytest.mark.integration
def test_aucun_incertain_quand_une_reponse_sure_existe(db_session):
    """Une piste à côté d'une réponse sûre ne ferait que la diluer."""
    _, sure = seed_ticket_reponse(db_session, statut="VALIDÉE", canonique=True, nb_validations=3, faq_visible=True)
    _, faible = seed_ticket_reponse(db_session, statut="VALIDÉE", canonique=True, nb_validations=3, faq_visible=True)

    with patch(
        "app.services.faq.rechercher_points_reponses",
        return_value=[point(sure.id, SEUIL + 0.10), point(faible.id, SEUIL - 0.05)],
    ):
        rangs = rechercher_faq(db_session, "peu importe", 5)

    assert len(rangs["resultats"]) == 1
    assert rangs["incertains"] == []


@pytest.mark.integration
@pytest.mark.parametrize("q", ["", "  ", "ab"], ids=["vide", "espaces", "trop court"])
def test_question_trop_courte_rejetee(client, db_session, auth_header, q):
    """Rejeté avant tout appel Albert."""
    from .helpers_reponses import make_user

    user = make_user(db_session)
    db_session.commit()

    resp = client.get(f"{API}/faq/recherche", params={"q": q}, headers=auth_header(user))

    assert resp.status_code == 422
