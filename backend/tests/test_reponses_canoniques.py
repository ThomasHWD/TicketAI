"""Tests du listing et de la gestion des réponses canoniques et obsolètes."""

import pytest

from .helpers_reponses import API, rendre_obsolete, seed_ticket_reponse, signaler

pytestmark = pytest.mark.integration


# --------------------------------------------------------------------------- #
# GET /reponses/en-attente  et  /reponses/canoniques
# --------------------------------------------------------------------------- #
def test_lister_en_attente_filtre_domaine(client, db_session, validator, auth_header):
    seed_ticket_reponse(db_session, domaine="IT")
    seed_ticket_reponse(db_session, domaine="RH")

    resp = client.get(f"{API}/reponses/en-attente", params={"domaine": "IT"}, headers=auth_header(validator))

    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 1
    assert items[0]["domaine"] == "IT"
    assert {"reponse_id", "ticket_id", "question", "reponse"} <= items[0].keys()


def test_lister_canoniques_pagination(client, db_session, validator, auth_header):
    _, source = seed_ticket_reponse(db_session, statut="VALIDÉE", canonique=True, nb_validations=3)
    seed_ticket_reponse(db_session, statut="VALIDÉE", canonique=True, reponse_source_id=source.id)

    resp = client.get(
        f"{API}/reponses/canoniques",
        params={"page": 1, "limit": 20},
        headers=auth_header(validator),
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["page"] == 1
    assert len(body["items"]) == 1
    assert body["items"][0]["reponse_id"] == str(source.id)


def test_canoniques_exclut_les_obsoletes(client, db_session, validator, auth_header):
    """Sans ce filtre, une réponse retirée du service passerait pour active."""

    _, active = seed_ticket_reponse(db_session, statut="VALIDÉE", canonique=True, nb_validations=3)
    _, perimee = seed_ticket_reponse(db_session, statut="VALIDÉE", canonique=True, nb_validations=3)
    rendre_obsolete(db_session, perimee)

    body = client.get(f"{API}/reponses/canoniques", headers=auth_header(validator)).json()

    assert [i["reponse_id"] for i in body["items"]] == [str(active.id)]


# --------------------------------------------------------------------------- #
# Obsolescence : GET /reponses/obsoletes, POST /reponses/{id}/restaurer
# --------------------------------------------------------------------------- #
def test_lister_obsoletes(client, db_session, validator, auth_header):
    _, reponse = seed_ticket_reponse(db_session, statut="VALIDÉE", canonique=True, nb_validations=4)
    rendre_obsolete(db_session, reponse)
    seed_ticket_reponse(db_session, statut="VALIDÉE", canonique=True)  # active, absente

    body = client.get(f"{API}/reponses/obsoletes", headers=auth_header(validator)).json()

    assert body["total"] == 1
    item = body["items"][0]
    assert item["reponse_id"] == str(reponse.id)
    assert item["obsolete_raison"] == "DOC_MIS_A_JOUR"
    assert item["obsolete_version"] == 2
    assert item["nb_validations"] == 4
    assert item["canonique"] is True


def test_lister_obsoletes_inclut_les_non_canoniques(client, db_session, validator, auth_header):
    """Une VALIDÉE pas encore promue peut devenir obsolète et doit rester visible."""
    _, reponse = seed_ticket_reponse(db_session, statut="VALIDÉE", canonique=False, nb_validations=1)
    rendre_obsolete(db_session, reponse)

    body = client.get(f"{API}/reponses/obsoletes", headers=auth_header(validator)).json()

    assert [i["reponse_id"] for i in body["items"]] == [str(reponse.id)]


def test_lister_obsoletes_masque_les_copies(client, db_session, validator, auth_header):
    _, source = seed_ticket_reponse(db_session, statut="VALIDÉE", canonique=True)
    _, copie = seed_ticket_reponse(db_session, statut="VALIDÉE", reponse_source_id=source.id)
    rendre_obsolete(db_session, source)
    rendre_obsolete(db_session, copie)

    body = client.get(f"{API}/reponses/obsoletes", headers=auth_header(validator)).json()

    assert [i["reponse_id"] for i in body["items"]] == [str(source.id)]


def test_lister_obsoletes_document_supprime(client, db_session, validator, auth_header):
    """Jointure externe : le document déclencheur peut ne plus exister en base."""
    _, reponse = seed_ticket_reponse(db_session, statut="VALIDÉE", canonique=True)
    rendre_obsolete(db_session, reponse, doc_id="doc-disparu", raison="DOC_SUPPRIMÉ")

    item = client.get(f"{API}/reponses/obsoletes", headers=auth_header(validator)).json()["items"][0]

    assert item["doc_id"] == "doc-disparu"
    assert item["document_filename"] is None
    assert item["document_supprime"] is True


def test_lister_obsoletes_filtre_domaine(client, db_session, validator, auth_header):
    _, it = seed_ticket_reponse(db_session, statut="VALIDÉE", domaine="IT")
    _, rh = seed_ticket_reponse(db_session, statut="VALIDÉE", domaine="RH")
    rendre_obsolete(db_session, it)
    rendre_obsolete(db_session, rh)

    body = client.get(f"{API}/reponses/obsoletes", params={"domaine": "IT"}, headers=auth_header(validator)).json()

    assert [i["reponse_id"] for i in body["items"]] == [str(it.id)]


def test_restaurer_leve_le_drapeau_et_reindexe(client, db_session, validator, auth_header, mock_side_effects):
    from app.models.reponse import Reponse

    _, reponse = seed_ticket_reponse(db_session, statut="VALIDÉE", canonique=True, nb_validations=3)
    rendre_obsolete(db_session, reponse)

    resp = client.post(f"{API}/reponses/{reponse.id}/restaurer", headers=auth_header(validator))

    assert resp.status_code == 200
    db_session.expunge_all()
    restauree = db_session.get(Reponse, reponse.id)
    assert restauree.obsolete is False
    assert restauree.obsolete_raison is None
    assert restauree.obsolete_doc_id is None
    assert restauree.obsolete_at is None
    assert restauree.nb_validations == 3
    assert mock_side_effects.feedback.called


def test_restaurer_remonte_toute_la_famille(client, db_session, validator, auth_header, mock_side_effects):
    """`marquer_obsoletes` a retiré les points de la source ET de ses copies :
    la restauration doit être symétrique, sinon les copies restent muettes."""
    from app.models.reponse import Reponse

    _, source = seed_ticket_reponse(db_session, statut="VALIDÉE", canonique=True)
    _, copie = seed_ticket_reponse(db_session, statut="VALIDÉE", reponse_source_id=source.id)
    rendre_obsolete(db_session, source)
    rendre_obsolete(db_session, copie)
    copie_id = copie.id

    resp = client.post(f"{API}/reponses/{source.id}/restaurer", headers=auth_header(validator))

    assert resp.json()["nb_restaurees"] == 2
    db_session.expunge_all()
    assert db_session.get(Reponse, copie_id).obsolete is False


@pytest.mark.parametrize(
    ("source_copie", "statut_copie", "indexation_copie"),
    [
        ("SUGGESTION", "VALIDÉE", "alias"),  # formulation validée : alias de la source, rejugé
        ("CANONIQUE", "VALIDÉE", None),  # servie sans revue : n'a jamais eu de point
        ("SUGGESTION", "CORRIGÉE", "propre"),  # corrigée : indexée sous sa question, comme « Corriger »
    ],
)
def test_restaurer_ne_fait_pas_d_une_copie_une_source(
    client, db_session, validator, auth_header, mock_side_effects, source_copie, statut_copie, indexation_copie
):
    """Indexée seule, une copie servait son texte figé, aveugle aux éditions de la source
    (29/09/2026 : source éditée à 400 €, la question est revenue en SUGGESTION d'une copie à 300 €)."""
    _, source = seed_ticket_reponse(db_session, statut="VALIDÉE", canonique=True)
    _, copie = seed_ticket_reponse(db_session, statut=statut_copie, reponse_source_id=source.id)
    copie.source = source_copie
    db_session.commit()
    rendre_obsolete(db_session, source)
    rendre_obsolete(db_session, copie)
    s, c = str(source.id), str(copie.id)

    client.post(f"{API}/reponses/{s}/restaurer", headers=auth_header(validator))

    indexations = [tuple(appel.kwargs["args"]) for appel in mock_side_effects.feedback.call_args_list]
    attendu = {None: [(s,)], "alias": [(s,), (s, c)], "propre": [(s,), (c,)]}[indexation_copie]
    assert sorted(indexations) == sorted(attendu)


def test_restaurer_non_obsolete_renvoie_409(client, db_session, validator, auth_header):
    _, reponse = seed_ticket_reponse(db_session, statut="VALIDÉE", canonique=True)

    resp = client.post(f"{API}/reponses/{reponse.id}/restaurer", headers=auth_header(validator))

    assert resp.status_code == 409


def test_restaurer_hors_domaine_renvoie_403(client, db_session, validator, auth_header):
    _, reponse = seed_ticket_reponse(db_session, statut="VALIDÉE", domaine="RH")
    rendre_obsolete(db_session, reponse)

    resp = client.post(f"{API}/reponses/{reponse.id}/restaurer", headers=auth_header(validator))

    assert resp.status_code == 403


def test_supprimer_obsolete_non_canonique_autorise(client, db_session, validator, auth_header):
    """L'onglet Obsolètes peut purger une réponse non canonique : retrait Qdrant + obsolete=False.
    La ligne DB est conservée pour que le fil de conversation du ticket reste visible."""
    from app.models.reponse import Reponse

    _, reponse = seed_ticket_reponse(db_session, statut="VALIDÉE", canonique=False)
    rendre_obsolete(db_session, reponse)

    resp = client.delete(f"{API}/reponses/{reponse.id}", headers=auth_header(validator))

    assert resp.status_code == 200
    db_session.expunge_all()
    après = db_session.get(Reponse, reponse.id)
    assert après is not None
    assert après.obsolete is False


def test_supprimer_preserve_copies_validees_meme_si_obsoletes(client, db_session, validator, auth_header):
    """Les copies VALIDÉE obsolètes sont conservées en DB pour le fil historique du ticket.
    Seul le retrait Qdrant est effectué ; le flag obsolete est effacé."""
    from app.models.reponse import Reponse

    _, source = seed_ticket_reponse(db_session, statut="VALIDÉE", canonique=True)
    _, copie = seed_ticket_reponse(db_session, statut="VALIDÉE", reponse_source_id=source.id)
    rendre_obsolete(db_session, source)
    rendre_obsolete(db_session, copie)
    signaler(db_session, copie)
    copie_id = copie.id

    resp = client.delete(f"{API}/reponses/{source.id}", headers=auth_header(validator))

    assert resp.status_code == 200
    db_session.expunge_all()
    assert db_session.get(Reponse, copie_id) is not None
