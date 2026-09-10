"""Tests des endpoints GET /tags et PATCH /reponses/{id}/tag."""

import pytest

from .helpers_reponses import API, seed_ticket_reponse

pytestmark = pytest.mark.integration


def _seed_canonique(db, tag=None, domaine="IT"):
    _, r = seed_ticket_reponse(db, statut="VALIDÉE", canonique=True, nb_validations=3, domaine=domaine)
    if tag:
        r.tag = tag
        db.commit()
    return r


# --------------------------------------------------------------------------- #
# GET /tags
# --------------------------------------------------------------------------- #
def test_lister_tags_renvoie_tableau_vide_sans_donnees(client, db_session, validator, auth_header):
    resp = client.get(f"{API}/tags", headers=auth_header(validator))
    assert resp.status_code == 200
    assert resp.json() == []


def test_lister_tags_retourne_tags_canoniques(client, db_session, validator, auth_header):
    _seed_canonique(db_session, tag="congés")
    _seed_canonique(db_session, tag="paie")

    resp = client.get(f"{API}/tags?canoniques=true", headers=auth_header(validator))

    assert resp.status_code == 200
    assert sorted(resp.json()) == ["congés", "paie"]


def test_lister_tags_exclut_non_canoniques_quand_canoniques_true(client, db_session, validator, auth_header):
    _seed_canonique(db_session, tag="congés")
    # EN_ATTENTE avec tag — ne doit pas apparaître en mode canoniques
    _, en_attente = seed_ticket_reponse(db_session, statut="EN_ATTENTE")
    en_attente.tag = "brouillon"
    db_session.commit()

    resp = client.get(f"{API}/tags?canoniques=true", headers=auth_header(validator))

    assert "brouillon" not in resp.json()
    assert "congés" in resp.json()


def test_lister_tags_sans_filtre_inclut_toutes_reponses(client, db_session, validator, auth_header):
    _seed_canonique(db_session, tag="congés")
    _, en_attente = seed_ticket_reponse(db_session, statut="EN_ATTENTE")
    en_attente.tag = "brouillon"
    db_session.commit()

    resp = client.get(f"{API}/tags", headers=auth_header(validator))

    tags = resp.json()
    assert "congés" in tags
    assert "brouillon" in tags


def test_lister_tags_deduplique(client, db_session, validator, auth_header):
    _seed_canonique(db_session, tag="congés")
    _seed_canonique(db_session, tag="congés")  # doublon

    resp = client.get(f"{API}/tags?canoniques=true", headers=auth_header(validator))

    assert resp.json().count("congés") == 1


def test_lister_tags_trie_alphabetiquement(client, db_session, validator, auth_header):
    for t in ["paie", "arrêt maladie", "congés"]:
        _seed_canonique(db_session, tag=t)

    resp = client.get(f"{API}/tags?canoniques=true", headers=auth_header(validator))

    assert resp.json() == sorted(resp.json())


def test_lister_tags_exclut_obsoletes_quand_canoniques_true(client, db_session, validator, auth_header):
    r = _seed_canonique(db_session, tag="périmé")
    r.obsolete = True
    db_session.commit()
    _seed_canonique(db_session, tag="actif")

    resp = client.get(f"{API}/tags?canoniques=true", headers=auth_header(validator))

    assert "périmé" not in resp.json()
    assert "actif" in resp.json()


# --------------------------------------------------------------------------- #
# PATCH /reponses/{id}/tag
# --------------------------------------------------------------------------- #
def test_patch_tag_persist(client, db_session, validator, auth_header):
    from app.models.reponse import Reponse

    _, reponse = seed_ticket_reponse(db_session)

    resp = client.patch(
        f"{API}/reponses/{reponse.id}/tag",
        json={"tag": "  congés  "},
        headers=auth_header(validator),
    )

    assert resp.status_code == 200
    assert resp.json()["tag"] == "congés"
    db_session.expire_all()
    assert db_session.get(Reponse, reponse.id).tag == "congés"


def test_patch_tag_null_efface(client, db_session, validator, auth_header):
    from app.models.reponse import Reponse

    _, reponse = seed_ticket_reponse(db_session)
    reponse.tag = "à supprimer"
    db_session.commit()

    resp = client.patch(
        f"{API}/reponses/{reponse.id}/tag",
        json={"tag": None},
        headers=auth_header(validator),
    )

    assert resp.status_code == 200
    assert resp.json()["tag"] is None
    db_session.expire_all()
    assert db_session.get(Reponse, reponse.id).tag is None


def test_patch_tag_tronque_a_100(client, db_session, validator, auth_header):
    from app.models.reponse import Reponse

    _, reponse = seed_ticket_reponse(db_session)
    long_tag = "x" * 150

    resp = client.patch(
        f"{API}/reponses/{reponse.id}/tag",
        json={"tag": long_tag},
        headers=auth_header(validator),
    )

    assert resp.status_code == 200
    db_session.expire_all()
    assert len(db_session.get(Reponse, reponse.id).tag) == 100


def test_patch_tag_introuvable_renvoie_404(client, db_session, validator, auth_header):
    import uuid

    resp = client.patch(
        f"{API}/reponses/{uuid.uuid4()}/tag",
        json={"tag": "test"},
        headers=auth_header(validator),
    )

    assert resp.status_code == 404


def test_patch_tag_hors_domaine_renvoie_403(client, db_session, validator, auth_header):
    _, reponse = seed_ticket_reponse(db_session, domaine="RH")

    resp = client.patch(
        f"{API}/reponses/{reponse.id}/tag",
        json={"tag": "test"},
        headers=auth_header(validator),
    )

    assert resp.status_code == 403
