"""Tests des actions de validation : valider, rejeter, corriger, éditer, supprimer."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from .helpers_reponses import API, make_user, seed_ticket_reponse

pytestmark = pytest.mark.integration


def test_valider_sans_token_renvoie_401(client, db_session):
    _, reponse = seed_ticket_reponse(db_session)
    resp = client.post(f"{API}/reponses/{reponse.id}/valider")
    assert resp.status_code == 401


# --------------------------------------------------------------------------- #
# POST /reponses/{id}/valider
# --------------------------------------------------------------------------- #
def test_valider_transition_et_increment(client, db_session, validator, auth_header):
    from app.models.reponse import Reponse
    from app.models.ticket import Ticket

    _, reponse = seed_ticket_reponse(db_session)

    resp = client.post(
        f"{API}/reponses/{reponse.id}/valider",
        headers=auth_header(validator),
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["statut"] == "VALIDÉE"
    assert body["nb_validations"] == 1
    assert body["canonique"] is False

    db_session.expire_all()
    reloaded = db_session.get(Reponse, reponse.id)
    assert reloaded.statut == "VALIDÉE"
    assert reloaded.validated_at is not None
    assert reloaded.validator_id == validator.id
    ticket = db_session.get(Ticket, reloaded.ticket_id)
    assert ticket.statut_ticket == "VALIDÉ"


def test_valider_atteint_seuil_canonique(client, db_session, validator, auth_header):
    from app.config import settings
    from app.models.reponse import Reponse

    _, reponse = seed_ticket_reponse(db_session, nb_validations=settings.seuil_canonique - 1)

    resp = client.post(
        f"{API}/reponses/{reponse.id}/valider",
        headers=auth_header(validator),
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["nb_validations"] == settings.seuil_canonique
    assert body["canonique"] is True

    db_session.expire_all()
    assert db_session.get(Reponse, reponse.id).canonique is True


def test_valider_incremente_la_source_pas_la_copie(client, db_session, validator, auth_header):
    """Branche SUGGESTION : le compteur monte sur la source, pas sur la copie."""
    from app.models.reponse import Reponse

    _, source = seed_ticket_reponse(db_session, statut="VALIDÉE", nb_validations=1)
    _, copie = seed_ticket_reponse(db_session, reponse_source_id=source.id)

    resp = client.post(
        f"{API}/reponses/{copie.id}/valider",
        headers=auth_header(validator),
    )

    assert resp.status_code == 200
    db_session.expire_all()
    assert db_session.get(Reponse, source.id).nb_validations == 2
    assert db_session.get(Reponse, copie.id).nb_validations == 0


def test_valider_copies_suggestion_promeut_source_en_canonique(
    client, db_session, validator, auth_header, mock_side_effects
):
    """Valider N copies SUGGESTION doit promouvoir la SOURCE en canonique.

    C'est le scénario de régression BM25 : avant le fix, un chunk BM25-dominant
    à faible cosinus rendait servable=False et les copies ne se créaient plus,
    bloquant nb_validations sous le seuil. On vérifie ici que l'API promeut
    bien la source après (seuil_canonique - 1) copies validées en chaîne.
    """
    from app.config import settings
    from app.models.reponse import Reponse

    seuil = settings.seuil_canonique  # 3 par défaut

    # Source : déjà validée une première fois (1re validation directe)
    _, source = seed_ticket_reponse(db_session, statut="VALIDÉE", nb_validations=1)

    # On simule (seuil - 1) validations de copies SUGGESTION successives.
    for i in range(seuil - 1):
        _, copie = seed_ticket_reponse(db_session, reponse_source_id=source.id)

        resp = client.post(
            f"{API}/reponses/{copie.id}/valider",
            headers=auth_header(validator),
        )
        assert resp.status_code == 200, f"Échec à la copie #{i + 1}"

        db_session.expire_all()
        source_en_base = db_session.get(Reponse, source.id)
        attendu = 1 + (i + 1)
        assert source_en_base.nb_validations == attendu, (
            f"Après copie #{i + 1} : nb_validations={source_en_base.nb_validations}, attendu {attendu}"
        )

    # Après (seuil - 1) copies, la source doit être canonique
    db_session.expire_all()
    source_finale = db_session.get(Reponse, source.id)
    assert source_finale.nb_validations == seuil
    assert source_finale.canonique is True, (
        f"La source doit être canonique après {seuil} validations, "
        f"mais canonique={source_finale.canonique} (nb_validations={source_finale.nb_validations})"
    )


def test_valider_reponse_source_declenche_reindexation(client, db_session, validator, auth_header, mock_side_effects):
    _, reponse = seed_ticket_reponse(db_session)

    client.post(
        f"{API}/reponses/{reponse.id}/valider",
        headers=auth_header(validator),
    )

    assert mock_side_effects.feedback.called


def test_valider_etat_final_renvoie_409(client, db_session, validator, auth_header):
    _, reponse = seed_ticket_reponse(db_session, statut="REJETÉE")

    resp = client.post(
        f"{API}/reponses/{reponse.id}/valider",
        headers=auth_header(validator),
    )

    assert resp.status_code == 409


def test_brouillon_retire_ni_liste_ni_validable(client, db_session, validator, auth_header):
    """Un brouillon retiré (source contredite) reste EN_ATTENTE : sans filtre, la file
    le proposait et le valider servait une réponse jugée fausse."""
    _, reponse = seed_ticket_reponse(db_session)
    reponse.obsolete = True
    db_session.commit()

    file = client.get(f"{API}/reponses/en-attente", headers=auth_header(validator))
    resp = client.post(f"{API}/reponses/{reponse.id}/valider", headers=auth_header(validator))

    assert str(reponse.id) not in [r["reponse_id"] for r in file.json()]
    assert resp.status_code == 409


def test_valider_auto_validation_renvoie_403(client, db_session, auth_header):
    from app.models.groupe import Groupe

    user = make_user(db_session)
    groupe = Groupe(nom="IT", domaine="IT")
    db_session.add(groupe)
    db_session.flush()
    groupe.membres.append(user)
    db_session.commit()
    db_session.refresh(user)
    _, reponse = seed_ticket_reponse(db_session, user_id=user.id)

    resp = client.post(
        f"{API}/reponses/{reponse.id}/valider",
        headers=auth_header(user),
    )

    assert resp.status_code == 403


def test_valider_ticket_verrouille_par_autre_renvoie_409(client, db_session, validator, auth_header):
    locker = make_user(db_session)
    db_session.commit()
    _, reponse = seed_ticket_reponse(
        db_session,
        locked_by=locker.id,
        lock_expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
    )

    resp = client.post(
        f"{API}/reponses/{reponse.id}/valider",
        headers=auth_header(validator),
    )

    assert resp.status_code == 409


def test_valider_introuvable_renvoie_404(client, db_session, validator, auth_header):
    resp = client.post(
        f"{API}/reponses/{uuid.uuid4()}/valider",
        headers=auth_header(validator),
    )
    assert resp.status_code == 404


# --------------------------------------------------------------------------- #
# POST /reponses/{id}/rejeter
# --------------------------------------------------------------------------- #
def test_rejeter_transition(client, db_session, validator, auth_header):
    from app.models.reponse import Reponse
    from app.models.ticket import Ticket

    _, reponse = seed_ticket_reponse(db_session)

    resp = client.post(
        f"{API}/reponses/{reponse.id}/rejeter",
        json={"raison": "hors sujet"},
        headers=auth_header(validator),
    )

    assert resp.status_code == 200
    assert resp.json()["statut"] == "REJETÉE"
    db_session.expire_all()
    assert db_session.get(Reponse, reponse.id).statut == "REJETÉE"
    ticket = db_session.get(Ticket, reponse.ticket_id)
    assert ticket.statut_ticket == "REJETÉ"


# --------------------------------------------------------------------------- #
# PUT /reponses/{id}/corriger
# --------------------------------------------------------------------------- #
def test_corriger_transition(client, db_session, validator, auth_header):
    from app.models.reponse import Reponse

    _, reponse = seed_ticket_reponse(db_session)

    resp = client.put(
        f"{API}/reponses/{reponse.id}/corriger",
        json={"contenu_corrige": "Texte corrigé"},
        headers=auth_header(validator),
    )

    assert resp.status_code == 200
    db_session.expire_all()
    reloaded = db_session.get(Reponse, reponse.id)
    assert reloaded.statut == "CORRIGÉE"
    assert reloaded.contenu_corrige == "Texte corrigé"


@pytest.mark.parametrize(
    "jugee_equivalente, oui_d_un_autre_tour, propagee",
    [
        pytest.param(True, False, True, id="oui-sur-cette-question"),
        pytest.param(False, False, False, id="sans-verdict-favorable"),
        pytest.param(False, True, False, id="oui-du-tour-initial-ne-vaut-pas-pour-le-suivi"),
    ],
)
def test_corriger_suggestion_ne_propage_que_si_le_juge_a_dit_oui(
    client, db_session, validator, auth_header, jugee_equivalente, oui_d_un_autre_tour, propagee
):
    """Correction de détail sur la même question (juge OUI) : la canonique en profite.
    SUGGESTION servie sans verdict favorable (panne Albert, refus) : elle peut être un cas
    spécifique d'une générale — la réécrire servirait la réponse spécifique à tous.

    Le OUI doit porter sur la question de CETTE copie. Cherché par ticket, celui du tour initial
    couvrait le suivi « et pour un apprenti ? » servi pendant une panne du juge : la correction
    « apprentis : 28 jours » réécrivait la canonique générale."""
    from app.models.garde_decision import GardeDecision
    from app.models.reponse import Reponse

    _, source = seed_ticket_reponse(db_session, statut="VALIDÉE", canonique=True)
    ticket, copie = seed_ticket_reponse(db_session, reponse_source_id=source.id)
    copie.jugee_equivalente = jugee_equivalente
    if oui_d_un_autre_tour:
        db_session.add(GardeDecision(job_id=ticket.job_id, question_posee="q", question_indexee="q",
                                     reponse_id=source.id, verdict=True))
    db_session.commit()

    resp = client.put(
        f"{API}/reponses/{copie.id}/corriger",
        json={"contenu_corrige": "Texte corrigé"},
        headers=auth_header(validator),
    )

    assert resp.status_code == 200
    db_session.expire_all()
    assert (db_session.get(Reponse, source.id).contenu_corrige == "Texte corrigé") is propagee
    assert db_session.get(Reponse, copie.id).contenu_corrige == "Texte corrigé"


def test_corriger_contenu_vide_renvoie_400(client, db_session, validator, auth_header):
    _, reponse = seed_ticket_reponse(db_session)

    resp = client.put(
        f"{API}/reponses/{reponse.id}/corriger",
        json={"contenu_corrige": "   "},
        headers=auth_header(validator),
    )

    assert resp.status_code == 400


# --------------------------------------------------------------------------- #
# PUT /reponses/{id}/editer  (canoniques — back-office ayant le domaine)
# --------------------------------------------------------------------------- #
def test_editer_hors_backoffice_renvoie_403(client, db_session, auth_headers):
    _, reponse = seed_ticket_reponse(db_session, statut="VALIDÉE", canonique=True)

    resp = client.put(
        f"{API}/reponses/{reponse.id}/editer",
        json={"contenu": "Nouveau contenu servi"},
        headers=auth_headers,
    )

    assert resp.status_code == 403


def test_editer_hors_domaine_renvoie_403(client, db_session, validator, auth_header):
    """Le droit suit le domaine du ticket, pas le rôle : le validateur IT n'édite
    pas une canonique RH, exactement comme il ne remplacerait pas un document RH."""
    _, reponse = seed_ticket_reponse(db_session, statut="VALIDÉE", canonique=True, domaine="RH")

    resp = client.put(
        f"{API}/reponses/{reponse.id}/editer",
        json={"contenu": "Nouveau contenu servi"},
        headers=auth_header(validator),
    )

    assert resp.status_code == 403


def test_editer_canonique_ok(client, db_session, validator, auth_header):
    from app.models.reponse import Reponse

    _, reponse = seed_ticket_reponse(db_session, statut="VALIDÉE", canonique=True)

    resp = client.put(
        f"{API}/reponses/{reponse.id}/editer",
        json={"contenu": "Nouveau contenu servi"},
        headers=auth_header(validator),
    )

    assert resp.status_code == 200
    db_session.expire_all()
    assert db_session.get(Reponse, reponse.id).contenu_corrige == "Nouveau contenu servi"


def test_editer_non_canonique_renvoie_409(client, db_session, validator, auth_header):
    _, reponse = seed_ticket_reponse(db_session, canonique=False)

    resp = client.put(
        f"{API}/reponses/{reponse.id}/editer",
        json={"contenu": "Peu importe"},
        headers=auth_header(validator),
    )

    assert resp.status_code == 409


def test_editer_contenu_vide_renvoie_400(client, db_session, validator, auth_header):
    _, reponse = seed_ticket_reponse(db_session, statut="VALIDÉE", canonique=True)

    resp = client.put(
        f"{API}/reponses/{reponse.id}/editer",
        json={"contenu": "  "},
        headers=auth_header(validator),
    )

    assert resp.status_code == 400


# --------------------------------------------------------------------------- #
# DELETE /reponses/{id}  (canoniques — back-office ayant le domaine)
# --------------------------------------------------------------------------- #
def test_supprimer_hors_domaine_renvoie_403(client, db_session, validator, auth_header):
    _, reponse = seed_ticket_reponse(db_session, statut="VALIDÉE", canonique=True, domaine="RH")

    resp = client.delete(f"{API}/reponses/{reponse.id}", headers=auth_header(validator))

    assert resp.status_code == 403


def test_supprimer_non_canonique_renvoie_409(client, db_session, validator, auth_header):
    _, reponse = seed_ticket_reponse(db_session, canonique=False)

    resp = client.delete(f"{API}/reponses/{reponse.id}", headers=auth_header(validator))

    assert resp.status_code == 409


def test_supprimer_canonique_preserve_reponses_validees(client, db_session, validator, auth_header, mock_side_effects):
    """Les réponses VALIDÉE/CORRIGÉE restent en DB pour le fil historique du ticket."""
    from app.models.reponse import Reponse

    _, source = seed_ticket_reponse(db_session, statut="VALIDÉE", canonique=True)
    _, copie = seed_ticket_reponse(db_session, statut="VALIDÉE", canonique=True, reponse_source_id=source.id)

    resp = client.delete(f"{API}/reponses/{source.id}", headers=auth_header(validator))

    assert resp.status_code == 200
    assert mock_side_effects.delete_point.called
    db_session.expunge_all()
    assert db_session.get(Reponse, source.id).canonique is False
    assert db_session.get(Reponse, copie.id).canonique is False


def test_supprimer_canonique_preserve_copies_obsoletes(
    client, db_session, validator, auth_header, mock_side_effects
):
    """Une copie VALIDÉE/CORRIGÉE obsolète est conservée en DB pour le fil historique,
    même si elle était hors service. La source est dépromue et retirée de l'onglet Obsolètes."""
    from app.models.reponse import Reponse

    _, source = seed_ticket_reponse(db_session, statut="VALIDÉE", canonique=True)
    _, copie = seed_ticket_reponse(db_session, statut="VALIDÉE", canonique=False, reponse_source_id=source.id)
    copie.obsolete = True
    copie.obsolete_raison = "DOC_MIS_A_JOUR"
    copie.obsolete_at = datetime.now(timezone.utc)
    source.obsolete = True
    source.obsolete_raison = "DOC_MIS_A_JOUR"
    source.obsolete_at = datetime.now(timezone.utc)
    source_id = source.id
    copie_id = copie.id
    db_session.commit()

    resp = client.delete(f"{API}/reponses/{source_id}", headers=auth_header(validator))

    assert resp.status_code == 200
    db_session.expunge_all()
    source_après = db_session.get(Reponse, source_id)
    assert source_après.canonique is False
    assert source_après.obsolete is False
    assert db_session.get(Reponse, copie_id).canonique is False


def test_supprimer_canonique_nettoie_les_chunks(client, db_session, validator, auth_header):
    from app.models.reponse_chunk import ReponseChunk

    _, reponse = seed_ticket_reponse(db_session, statut="VALIDÉE", canonique=True)
    db_session.add(ReponseChunk(reponse_id=reponse.id, doc_id="doc-1", chunk_index=0))
    db_session.commit()

    reponse_id = reponse.id
    resp = client.delete(f"{API}/reponses/{reponse_id}", headers=auth_header(validator))

    assert resp.status_code == 200
    db_session.expunge_all()
    remaining = db_session.query(ReponseChunk).filter(ReponseChunk.reponse_id == reponse_id).count()
    assert remaining == 0
