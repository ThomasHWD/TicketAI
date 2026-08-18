"""Tests de l'onglet À relire : signalement, confirmer-actualite, retirer."""

import pytest

from .helpers_reponses import API, rendre_obsolete, seed_ticket_reponse, signaler

pytestmark = pytest.mark.integration


def test_lister_a_relire(client, db_session, validator, auth_header):
    _, signalee = seed_ticket_reponse(db_session, statut="VALIDÉE", canonique=True, nb_validations=4)
    signaler(db_session, signalee)
    seed_ticket_reponse(db_session, statut="VALIDÉE", canonique=True)  # non signalée, absente

    body = client.get(f"{API}/reponses/a-relire", headers=auth_header(validator)).json()

    assert body["total"] == 1
    item = body["items"][0]
    assert item["reponse_id"] == str(signalee.id)
    assert item["a_relire_raison"] == "DOC_MODIFIÉ"
    assert item["a_relire_version"] == 3
    assert item["doc_id"] == "doc-modifie"


def test_lister_a_relire_compte_les_documents_pas_les_reponses(client, db_session, validator, auth_header):
    """Le badge de la sidebar compte les documents : « 2 documents à relire » se
    traite, « 39 réponses » se subit."""
    for _ in range(3):
        _, r = seed_ticket_reponse(db_session, statut="VALIDÉE", canonique=True)
        signaler(db_session, r, doc_id="charte-rh")
    _, autre = seed_ticket_reponse(db_session, statut="VALIDÉE", canonique=True)
    signaler(db_session, autre, doc_id="reglement-it")

    body = client.get(f"{API}/reponses/a-relire", headers=auth_header(validator)).json()

    assert body["total"] == 4
    assert body["nb_documents"] == 2


def test_lister_a_relire_remonte_les_changements(client, db_session, validator, auth_header):
    """Sans les extraits, « cette réponse est liée à Charte_RH v3 » ne permet de
    juger de rien : c'est le diff qu'on relit, pas le numéro de version."""
    from app.models.document import Document
    from app.models.document_version import DocumentVersion

    db_session.add(Document(doc_id="charte-rh", filename="charte.md", domaine="IT", version=3))
    db_session.add(
        DocumentVersion(
            doc_id="charte-rh",
            version=3,
            filename="charte.md",
            changements={
                "nb_ajoutes": 1,
                "nb_retires": 0,
                "extraits_ajoutes": ["Article 7 bis…"],
                "extraits_retires": [],
            },
        )
    )
    _, reponse = seed_ticket_reponse(db_session, statut="VALIDÉE", canonique=True)
    signaler(db_session, reponse, doc_id="charte-rh", version=3)

    item = client.get(f"{API}/reponses/a-relire", headers=auth_header(validator)).json()["items"][0]

    assert item["document_filename"] == "charte.md"
    assert item["document_supprime"] is False
    assert item["changements"]["extraits_ajoutes"] == ["Article 7 bis…"]


def test_lister_a_relire_masque_les_copies(client, db_session, validator, auth_header):
    _, source = seed_ticket_reponse(db_session, statut="VALIDÉE", canonique=True)
    _, copie = seed_ticket_reponse(db_session, statut="VALIDÉE", reponse_source_id=source.id)
    signaler(db_session, source)
    signaler(db_session, copie)

    body = client.get(f"{API}/reponses/a-relire", headers=auth_header(validator)).json()

    assert [i["reponse_id"] for i in body["items"]] == [str(source.id)]


def test_lister_a_relire_filtre_domaine(client, db_session, validator, auth_header):
    _, it = seed_ticket_reponse(db_session, statut="VALIDÉE", domaine="IT")
    _, rh = seed_ticket_reponse(db_session, statut="VALIDÉE", domaine="RH")
    signaler(db_session, it)
    signaler(db_session, rh)

    body = client.get(f"{API}/reponses/a-relire", params={"domaine": "IT"}, headers=auth_header(validator)).json()

    assert [i["reponse_id"] for i in body["items"]] == [str(it.id)]


def test_confirmer_actualite_leve_le_signalement(client, db_session, validator, auth_header):
    from app.models.reponse import Reponse

    _, reponse = seed_ticket_reponse(db_session, statut="VALIDÉE", canonique=True, nb_validations=3)
    signaler(db_session, reponse)

    resp = client.post(f"{API}/reponses/{reponse.id}/confirmer-actualite", headers=auth_header(validator))

    assert resp.status_code == 200
    db_session.expunge_all()
    confirmee = db_session.get(Reponse, reponse.id)
    assert confirmee.a_relire is False
    assert confirmee.a_relire_doc_id is None
    assert confirmee.obsolete is False
    assert confirmee.nb_validations == 3


def test_confirmer_actualite_remonte_toute_la_famille(client, db_session, validator, auth_header):
    """Le drapeau a été posé sur la famille entière : le lever sur la seule source
    laisserait les copies signalées, sans aucune issue puisque la liste ne montre
    que les sources."""
    from app.models.reponse import Reponse

    _, source = seed_ticket_reponse(db_session, statut="VALIDÉE", canonique=True)
    _, copie = seed_ticket_reponse(db_session, statut="VALIDÉE", reponse_source_id=source.id)
    signaler(db_session, source)
    signaler(db_session, copie)
    copie_id = copie.id

    client.post(f"{API}/reponses/{source.id}/confirmer-actualite", headers=auth_header(validator))

    db_session.expunge_all()
    assert db_session.get(Reponse, copie_id).a_relire is False


def test_confirmer_actualite_non_signalee_renvoie_409(client, db_session, validator, auth_header):
    _, reponse = seed_ticket_reponse(db_session, statut="VALIDÉE", canonique=True)

    resp = client.post(f"{API}/reponses/{reponse.id}/confirmer-actualite", headers=auth_header(validator))

    assert resp.status_code == 409


def test_confirmer_actualite_hors_domaine_renvoie_403(client, db_session, validator, auth_header):
    _, reponse = seed_ticket_reponse(db_session, statut="VALIDÉE", domaine="RH")
    signaler(db_session, reponse)

    resp = client.post(f"{API}/reponses/{reponse.id}/confirmer-actualite", headers=auth_header(validator))

    assert resp.status_code == 403


def test_confirmer_actualite_en_lot(client, db_session, validator, auth_header):
    """La sortie normale quand un document en a signalé des dizaines : on lit le
    diff une fois, on juge l'ensemble ensuite."""
    from app.models.reponse import Reponse

    ids = []
    for _ in range(3):
        _, r = seed_ticket_reponse(db_session, statut="VALIDÉE", canonique=True)
        signaler(db_session, r, doc_id="charte-rh", version=3)
        ids.append(r.id)
    _, autre_doc = seed_ticket_reponse(db_session, statut="VALIDÉE", canonique=True)
    signaler(db_session, autre_doc, doc_id="reglement-it", version=1)
    autre_id = autre_doc.id

    resp = client.post(
        f"{API}/reponses/confirmer-actualite",
        json={"doc_id": "charte-rh", "version": 3},
        headers=auth_header(validator),
    )

    assert resp.status_code == 200
    assert resp.json()["nb_confirmees"] == 3
    db_session.expunge_all()
    assert all(db_session.get(Reponse, i).a_relire is False for i in ids)
    assert db_session.get(Reponse, autre_id).a_relire is True


def test_confirmer_actualite_en_lot_borne_a_la_version(client, db_session, validator, auth_header):
    """Un document remis à jour entre-temps a reflagué sur v4 : une confirmation
    partie de l'écran de v3 ne doit pas balayer un signalement jamais vu."""
    from app.models.reponse import Reponse

    _, v3 = seed_ticket_reponse(db_session, statut="VALIDÉE", canonique=True)
    _, v4 = seed_ticket_reponse(db_session, statut="VALIDÉE", canonique=True)
    signaler(db_session, v3, doc_id="charte-rh", version=3)
    signaler(db_session, v4, doc_id="charte-rh", version=4)
    v4_id = v4.id

    resp = client.post(
        f"{API}/reponses/confirmer-actualite",
        json={"doc_id": "charte-rh", "version": 3},
        headers=auth_header(validator),
    )

    assert resp.json()["nb_confirmees"] == 1
    db_session.expunge_all()
    assert db_session.get(Reponse, v4_id).a_relire is True


def test_confirmer_actualite_en_lot_ignore_les_autres_domaines(client, db_session, validator, auth_header):
    """Un même document peut avoir servi à des tickets de plusieurs domaines : le
    lot confirme ce qui relève de l'appelant, sans échouer sur le reste."""
    from app.models.reponse import Reponse

    _, it = seed_ticket_reponse(db_session, statut="VALIDÉE", domaine="IT")
    _, rh = seed_ticket_reponse(db_session, statut="VALIDÉE", domaine="RH")
    signaler(db_session, it, doc_id="charte-rh", version=3)
    signaler(db_session, rh, doc_id="charte-rh", version=3)
    rh_id = rh.id

    resp = client.post(
        f"{API}/reponses/confirmer-actualite",
        json={"doc_id": "charte-rh", "version": 3},
        headers=auth_header(validator),
    )

    assert resp.json()["nb_confirmees"] == 1
    db_session.expunge_all()
    assert db_session.get(Reponse, rh_id).a_relire is True


def test_retirer_bascule_vers_obsoletes(client, db_session, validator, auth_header, mock_side_effects):
    """La troisième issue : la réponse est dépassée mais mérite de rester
    consultable — et restaurable."""
    from app.models.reponse import Reponse

    _, reponse = seed_ticket_reponse(db_session, statut="VALIDÉE", canonique=True)
    signaler(db_session, reponse, doc_id="charte-rh", version=3)

    resp = client.post(f"{API}/reponses/{reponse.id}/retirer", headers=auth_header(validator))

    assert resp.status_code == 200
    db_session.expunge_all()
    retiree = db_session.get(Reponse, reponse.id)
    assert retiree.obsolete is True
    assert retiree.obsolete_raison == "RETIRÉ_À_LA_MAIN"
    assert retiree.a_relire is False


def test_retirer_reprend_le_document_du_signalement(client, db_session, validator, auth_header, mock_side_effects):
    """Sans ce report, l'onglet Obsolètes afficherait « document supprimé »
    (jointure externe sans correspondance) pour une réponse retirée à la main sur
    un document bien vivant."""
    from app.models.reponse import Reponse

    _, reponse = seed_ticket_reponse(db_session, statut="VALIDÉE", canonique=True)
    signaler(db_session, reponse, doc_id="charte-rh", version=3)

    client.post(f"{API}/reponses/{reponse.id}/retirer", headers=auth_header(validator))

    db_session.expunge_all()
    retiree = db_session.get(Reponse, reponse.id)
    assert retiree.obsolete_doc_id == "charte-rh"
    assert retiree.obsolete_version == 3


def test_retirer_non_signalee_renvoie_409(client, db_session, validator, auth_header):
    _, reponse = seed_ticket_reponse(db_session, statut="VALIDÉE", canonique=True)

    resp = client.post(f"{API}/reponses/{reponse.id}/retirer", headers=auth_header(validator))

    assert resp.status_code == 409


def test_retirer_hors_domaine_renvoie_403(client, db_session, validator, auth_header):
    _, reponse = seed_ticket_reponse(db_session, statut="VALIDÉE", domaine="RH")
    signaler(db_session, reponse)

    resp = client.post(f"{API}/reponses/{reponse.id}/retirer", headers=auth_header(validator))

    assert resp.status_code == 403


def test_editer_signalee_non_canonique_autorise(client, db_session, validator, auth_header, mock_side_effects):
    """« Corriger » est l'une des trois issues du signalement : la refuser aux
    VALIDÉE pas encore promues ne laisserait que confirmer ou retirer."""
    from app.models.reponse import Reponse

    _, reponse = seed_ticket_reponse(db_session, statut="VALIDÉE", canonique=False)
    signaler(db_session, reponse)

    resp = client.put(
        f"{API}/reponses/{reponse.id}/editer",
        json={"contenu": "Texte remis à jour"},
        headers=auth_header(validator),
    )

    assert resp.status_code == 200
    db_session.expunge_all()
    editee = db_session.get(Reponse, reponse.id)
    assert editee.a_relire is False
    assert editee.contenu_corrige == "Texte remis à jour"


def test_restaurer_leve_aussi_le_signalement(client, db_session, validator, auth_header, mock_side_effects):
    """Restaurer *est* le jugement humain que le signalement réclamait : le
    reposer renverrait aussitôt la réponse dans l'onglet À relire."""
    from app.models.reponse import Reponse

    _, reponse = seed_ticket_reponse(db_session, statut="VALIDÉE", canonique=True)
    rendre_obsolete(db_session, reponse)
    signaler(db_session, reponse)

    client.post(f"{API}/reponses/{reponse.id}/restaurer", headers=auth_header(validator))

    db_session.expunge_all()
    restauree = db_session.get(Reponse, reponse.id)
    assert restauree.obsolete is False
    assert restauree.a_relire is False


def test_corriger_leve_le_signalement(client, db_session, validator, auth_header, mock_side_effects):
    """`reponses_obsoletes` ne retient que les VALIDÉE : une réponse signalée puis
    corrigée sortirait du périmètre en gardant son drapeau, et occuperait l'onglet
    sans qu'aucune action ne l'en déloge."""
    from app.models.reponse import Reponse

    _, reponse = seed_ticket_reponse(db_session, statut="EN_ATTENTE")
    signaler(db_session, reponse)

    resp = client.put(
        f"{API}/reponses/{reponse.id}/corriger",
        json={"contenu_corrige": "Texte corrigé"},
        headers=auth_header(validator),
    )

    assert resp.status_code == 200
    db_session.expunge_all()
    corrigee = db_session.get(Reponse, reponse.id)
    assert corrigee.statut == "CORRIGÉE"
    assert corrigee.a_relire is False
