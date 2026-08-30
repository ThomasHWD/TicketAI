"""Les filtres SQL du cache, exercés contre un **vrai** Postgres.

`trouver_reponse_reutilisable` décide en deux temps : un tri Python sur les scores
(couvert par `test_cache_over_hit.py`), puis un `WHERE` SQL qui exige
`statut == "VALIDÉE"` et `obsolete IS false` (`question_pipeline.py:157-160`).

Ce second temps est intestable avec une session mockée : un `MagicMock` renvoie
exactement ce qu'on a soufflé à `.all()`, donc un test « la réponse EN_ATTENTE est
écartée » passerait même si le filtre était supprimé du code. Il ne prouverait
rien. D'où ce module, marqué `integration` — exécuté en CI, auto-skippé en local
sans `make up` (cf. `conftest.py`).

Zéro appel réseau malgré tout : aucun Albert, aucun Qdrant. Seulement Postgres.
"""

import uuid

import pytest
from app.services import question_pipeline as qp

from .helpers_cosinus import chunk_factice
from .helpers_reponses import rendre_obsolete, seed_ticket_reponse

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _pas_de_sse(monkeypatch):
    """Cf. `test_cache_over_hit.py` : non neutralisé, le SSE coûte 2 s par appel."""
    monkeypatch.setattr(qp, "broadcast_sync", lambda *a, **k: None)


def chunks_pour(reponse, score=0.95):
    return [chunk_factice(score, reponse_id=str(reponse.id))]


# ══════════════════════════════════════════════════════════════════════════════
# Le filtre `statut` — seule une réponse VALIDÉE est réutilisable
# ══════════════════════════════════════════════════════════════════════════════


def test_une_reponse_validee_est_reutilisable(db_session):
    """Cas nominal : sans lui, les tests négatifs ci-dessous passeraient à vide."""
    _, reponse = seed_ticket_reponse(db_session, statut="VALIDÉE", canonique=True, nb_validations=3)

    trouvee, score = qp.trouver_reponse_reutilisable(db_session, chunks_pour(reponse))

    assert trouvee is not None
    assert trouvee.id == reponse.id
    assert score == 0.95


@pytest.mark.parametrize("statut", ["EN_ATTENTE", "REJETÉE", "CORRIGÉE"])
def test_seul_le_statut_validee_ouvre_le_cache(db_session, statut):
    """Une réponse non validée n'est jamais resservie, même à 0.95 de cosinus.

    Le cas CORRIGÉE mérite un mot : `servir_reutilisation` sert `contenu_corrige`
    en priorité (L202), ce qui pourrait laisser croire qu'une réponse CORRIGÉE est
    réutilisable. Elle ne l'est pas — le workflow repasse une correction en VALIDÉE
    pour l'ouvrir au cache. Les deux mécanismes se ressemblent sans se recouvrir.
    """
    _, reponse = seed_ticket_reponse(db_session, statut=statut, canonique=True, nb_validations=3)

    assert qp.trouver_reponse_reutilisable(db_session, chunks_pour(reponse)) == (None, None)


# ══════════════════════════════════════════════════════════════════════════════
# Le filtre `obsolete` — une réponse périmée ne revient pas par le cache
# ══════════════════════════════════════════════════════════════════════════════


def test_une_reponse_obsolete_n_est_plus_reutilisable(db_session):
    """Le drapeau d'obsolescence est la garantie de fin du pipeline de mise à jour.

    Sans ce filtre, une réponse retirée du service par `reverification_job`
    reviendrait par le cache dès la question suivante — le retrait ne serait qu'un
    affichage.
    """
    _, reponse = seed_ticket_reponse(db_session, statut="VALIDÉE", canonique=True, nb_validations=3)
    rendre_obsolete(db_session, reponse)

    assert qp.trouver_reponse_reutilisable(db_session, chunks_pour(reponse)) == (None, None)


def test_une_reponse_saine_est_preferee_a_une_obsolete_mieux_notee(db_session):
    """Le filtre s'applique avant le tri : l'obsolète n'est pas départagée, elle est exclue."""
    _, perimee = seed_ticket_reponse(db_session, statut="VALIDÉE", canonique=True, nb_validations=9)
    rendre_obsolete(db_session, perimee)
    _, saine = seed_ticket_reponse(db_session, statut="VALIDÉE", canonique=True, nb_validations=3)

    trouvee, score = qp.trouver_reponse_reutilisable(
        db_session,
        [chunk_factice(0.99, reponse_id=str(perimee.id)), chunk_factice(0.86, reponse_id=str(saine.id))],
    )

    assert trouvee.id == saine.id
    assert score == 0.86


# ══════════════════════════════════════════════════════════════════════════════
# Désynchronisation Qdrant / Postgres
# ══════════════════════════════════════════════════════════════════════════════


def test_un_reponse_id_fantome_ne_fait_pas_tomber_le_pipeline(db_session):
    """Un point Qdrant peut survivre à la disparition de sa ligne Postgres.

    Ce n'est pas hypothétique : la collection de développement contient des points
    portant un `reponse_id` dont la ligne n'existe plus. Les deux stockages ne
    partagent aucune transaction — toute suppression en base laisse une fenêtre, et
    tout `drop` de la base de test en laisse définitivement.

    Le comportement attendu est le repli silencieux sur le RAG, jamais une erreur :
    une désynchronisation d'index ne doit pas rendre une question insoluble.
    """
    chunks = [chunk_factice(0.99, reponse_id=str(uuid.uuid4()))]

    assert qp.trouver_reponse_reutilisable(db_session, chunks) == (None, None)


# ══════════════════════════════════════════════════════════════════════════════
# La boucle de rétroaction du compteur d'occurrences
# ══════════════════════════════════════════════════════════════════════════════


def test_chaque_service_canonique_incremente_le_compteur_de_la_source(db_session):
    """Un over-hit rend la question générique *plus populaire* — c'est une boucle.

    `question_pipeline.py:232-234` incrémente `occurence` sur le ticket source à
    chaque réutilisation canonique. Le compteur ne distingue pas une vraie
    redite d'une question précisée captée à tort : plus le cache sur-déclenche,
    plus la réponse générique paraît légitime dans tout classement qui consomme
    ce champ, et plus elle est susceptible d'être resservie.

    Test de caractérisation : il rend la boucle explicite et mesurable.
    """
    ticket_source, source = seed_ticket_reponse(db_session, statut="VALIDÉE", canonique=True, nb_validations=3)
    occurence_initiale = ticket_source.occurence

    qp.servir_reutilisation(
        db_session,
        uuid.uuid4(),
        None,
        "Question précisée pour un alternant ?",
        "IT",
        None,
        source,
        0.95,
        None,
        False,
        0,
        True,
    )

    db_session.expire_all()
    db_session.refresh(ticket_source)
    assert ticket_source.occurence == occurence_initiale + 1


def test_le_service_canonique_persiste_une_reponse_validee_liee_a_sa_source(db_session):
    """La copie servie pointe vers l'originale et n'est comptée nulle part comme validation.

    `nb_validations` est porté par la source, pas par la copie : le cache ne doit
    pas s'auto-promouvoir. Une copie qui incrémenterait son propre compteur
    atteindrait `seuil_canonique` sans qu'aucun humain n'ait jamais relu quoi que
    ce soit.
    """
    from app.models.reponse import Reponse

    _, source = seed_ticket_reponse(db_session, statut="VALIDÉE", canonique=True, nb_validations=3)

    resultat = qp.servir_reutilisation(
        db_session, uuid.uuid4(), None, "Question proche ?", "IT", None, source, 0.95, None, False, 0, True
    )

    db_session.expire_all()
    copie = db_session.query(Reponse).filter(Reponse.id == uuid.UUID(resultat["reponse_id"])).first()

    assert resultat["branche"] == "CANONIQUE"
    assert copie.reponse_source_id == source.id
    assert copie.statut == "VALIDÉE"
    assert copie.nb_validations == 0
    db_session.refresh(source)
    assert source.nb_validations == 3
