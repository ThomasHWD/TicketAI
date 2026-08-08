"""Tests d'intégration des routes de validation (`app/api/v1/reponses.py`).

Ces tests exercent les vraies routes FastAPI via ``TestClient`` contre une vraie
base Postgres de test (cf. ``conftest.py``). Ils complètent — sans les remplacer —
les tests unitaires des helpers dans ``test_endpoints.py``.

Depuis la mise en place de l'authentification, l'identité du validateur est
dérivée du JWT (header ``Authorization``) et non plus du corps de la requête.
Les fixtures ``auth_header`` / ``user_factory`` (conftest) émettent un vrai token
signé pour un utilisateur présent en base.

Marqués ``integration`` : exécutés sur GitHub Actions, auto-skippés en local sans
infra. Les effets de bord (Celery via ``feedback_job``, Qdrant via
``delete_response_point``) sont mockés par la fixture ``mock_side_effects``.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from app.config import settings
from app.models.groupe import Groupe
from app.models.reponse import Reponse
from app.models.reponse_chunk import ReponseChunk
from app.models.ticket import Ticket
from app.models.user import User

pytestmark = pytest.mark.integration

API = "/api/v1"


# --------------------------------------------------------------------------- #
# Helpers de seed
# --------------------------------------------------------------------------- #
def make_user(db, role="VALIDATEUR") -> User:
    user = User(email=f"{uuid.uuid4()}@test.local", role=role)
    db.add(user)
    db.flush()
    return user


@pytest.fixture
def validator(db_session):
    """Un validateur réellement présent en base, membre du groupe "IT".

    Son JWT sert d'identité pour les routes de validation
    (`reponses.validator_id` est une FK vers `users.id`).
    Le groupe "IT" correspond au domaine utilisé par défaut dans seed_ticket_reponse.
    """
    user = make_user(db_session)
    groupe = Groupe(nom="IT", domaine="IT")
    db_session.add(groupe)
    db_session.flush()
    groupe.membres.append(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def seed_ticket_reponse(
    db,
    *,
    statut="EN_ATTENTE",
    ticket_statut="RÉPONDU",
    user_id=None,
    reponse_source_id=None,
    canonique=False,
    nb_validations=0,
    contenu="Réponse test",
    contenu_corrige=None,
    locked_by=None,
    lock_expires_at=None,
    domaine="IT",
):
    """Crée un Ticket + sa Reponse et renvoie le couple (ticket, reponse)."""
    ticket = Ticket(
        question="Question test ?",
        domaine=domaine,
        user_id=user_id,
        statut_ticket=ticket_statut,
        locked_by=locked_by,
        lock_expires_at=lock_expires_at,
    )
    db.add(ticket)
    db.flush()

    reponse = Reponse(
        ticket_id=ticket.id,
        contenu=contenu,
        statut=statut,
        source="LLM",
        nb_validations=nb_validations,
        canonique=canonique,
        reponse_source_id=reponse_source_id,
        contenu_corrige=contenu_corrige,
    )
    db.add(reponse)
    db.commit()
    db.refresh(ticket)
    db.refresh(reponse)
    return ticket, reponse


# --------------------------------------------------------------------------- #
# Authentification requise
# --------------------------------------------------------------------------- #
def test_valider_sans_token_renvoie_401(client, db_session):
    _, reponse = seed_ticket_reponse(db_session)
    resp = client.post(f"{API}/reponses/{reponse.id}/valider")
    assert resp.status_code == 401


# --------------------------------------------------------------------------- #
# POST /reponses/{id}/valider
# --------------------------------------------------------------------------- #
def test_valider_transition_et_increment(client, db_session, validator, auth_header):
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
    # Une validation de plus doit atteindre le seuil et promouvoir en canonique.
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


def test_valider_reponse_source_declenche_reindexation(client, db_session, validator, auth_header, mock_side_effects):
    _, reponse = seed_ticket_reponse(db_session)

    client.post(
        f"{API}/reponses/{reponse.id}/valider",
        headers=auth_header(validator),
    )

    # feedback_job.apply_async doit être appelé pour réindexer dans Qdrant.
    assert mock_side_effects.feedback.called


def test_valider_etat_final_renvoie_409(client, db_session, validator, auth_header):
    _, reponse = seed_ticket_reponse(db_session, statut="REJETÉE")

    resp = client.post(
        f"{API}/reponses/{reponse.id}/valider",
        headers=auth_header(validator),
    )

    assert resp.status_code == 409


def test_valider_auto_validation_renvoie_403(client, db_session, auth_header):
    # L'utilisateur est à la fois membre du domaine IT ET créateur du ticket.
    user = make_user(db_session)
    groupe = Groupe(nom="IT", domaine="IT")
    db_session.add(groupe)
    db_session.flush()
    groupe.membres.append(user)
    db_session.commit()
    db_session.refresh(user)
    _, reponse = seed_ticket_reponse(db_session, user_id=user.id)

    # Même si l'utilisateur est backoffice, il ne peut pas valider son propre ticket.
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

    # `validator` n'est pas le détenteur du verrou → conflit.
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
        headers=auth_headers,  # rôle USER
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


def test_supprimer_canonique_detache_les_copies(client, db_session, validator, auth_header, mock_side_effects):
    _, source = seed_ticket_reponse(db_session, statut="VALIDÉE", canonique=True)
    _, copie = seed_ticket_reponse(db_session, statut="VALIDÉE", canonique=True, reponse_source_id=source.id)

    resp = client.delete(f"{API}/reponses/{source.id}", headers=auth_header(validator))

    assert resp.status_code == 200
    # Le point Qdrant est retiré (mock) et la source disparaît de la base.
    assert mock_side_effects.delete_point.called
    # expunge : le route a supprimé la ligne via SA propre session ; on vide
    # l'identity map pour re-lire l'état réel sans ObjectDeletedError.
    db_session.expunge_all()
    assert db_session.get(Reponse, source.id) is None
    # La copie est détachée et n'apparaît plus comme source canonique.
    reloaded_copie = db_session.get(Reponse, copie.id)
    assert reloaded_copie.reponse_source_id is None
    assert reloaded_copie.canonique is False


def test_supprimer_canonique_nettoie_les_chunks(client, db_session, validator, auth_header):
    _, reponse = seed_ticket_reponse(db_session, statut="VALIDÉE", canonique=True)
    db_session.add(ReponseChunk(reponse_id=reponse.id, doc_id="doc-1", chunk_index=0))
    db_session.commit()

    reponse_id = reponse.id
    resp = client.delete(f"{API}/reponses/{reponse_id}", headers=auth_header(validator))

    assert resp.status_code == 200
    db_session.expunge_all()
    remaining = db_session.query(ReponseChunk).filter(ReponseChunk.reponse_id == reponse_id).count()
    assert remaining == 0


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
    # Une source canonique visible + une copie (source renseignée) qui ne doit PAS
    # apparaître dans la liste.
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


# --------------------------------------------------------------------------- #
# Obsolescence : GET /reponses/obsoletes, POST /reponses/{id}/restaurer
# --------------------------------------------------------------------------- #
def _rendre_obsolete(db, reponse, *, doc_id="doc-obsolete", raison="DOC_MIS_A_JOUR", version=2):
    reponse.obsolete = True
    reponse.obsolete_raison = raison
    reponse.obsolete_doc_id = doc_id
    reponse.obsolete_version = version
    reponse.obsolete_at = datetime.now(timezone.utc)
    db.commit()
    return reponse


def test_canoniques_exclut_les_obsoletes(client, db_session, validator, auth_header):
    """Sans ce filtre, une réponse retirée du service passerait pour active."""
    _, active = seed_ticket_reponse(db_session, statut="VALIDÉE", canonique=True, nb_validations=3)
    _, perimee = seed_ticket_reponse(db_session, statut="VALIDÉE", canonique=True, nb_validations=3)
    _rendre_obsolete(db_session, perimee)

    body = client.get(f"{API}/reponses/canoniques", headers=auth_header(validator)).json()

    assert [i["reponse_id"] for i in body["items"]] == [str(active.id)]


def test_lister_obsoletes(client, db_session, validator, auth_header):
    _, reponse = seed_ticket_reponse(db_session, statut="VALIDÉE", canonique=True, nb_validations=4)
    _rendre_obsolete(db_session, reponse)
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
    _rendre_obsolete(db_session, reponse)

    body = client.get(f"{API}/reponses/obsoletes", headers=auth_header(validator)).json()

    assert [i["reponse_id"] for i in body["items"]] == [str(reponse.id)]


def test_lister_obsoletes_masque_les_copies(client, db_session, validator, auth_header):
    _, source = seed_ticket_reponse(db_session, statut="VALIDÉE", canonique=True)
    _, copie = seed_ticket_reponse(db_session, statut="VALIDÉE", reponse_source_id=source.id)
    _rendre_obsolete(db_session, source)
    _rendre_obsolete(db_session, copie)

    body = client.get(f"{API}/reponses/obsoletes", headers=auth_header(validator)).json()

    assert [i["reponse_id"] for i in body["items"]] == [str(source.id)]


def test_lister_obsoletes_document_supprime(client, db_session, validator, auth_header):
    """Jointure externe : le document déclencheur peut ne plus exister en base."""
    _, reponse = seed_ticket_reponse(db_session, statut="VALIDÉE", canonique=True)
    _rendre_obsolete(db_session, reponse, doc_id="doc-disparu", raison="DOC_SUPPRIMÉ")

    item = client.get(f"{API}/reponses/obsoletes", headers=auth_header(validator)).json()["items"][0]

    assert item["doc_id"] == "doc-disparu"
    assert item["document_filename"] is None
    assert item["document_supprime"] is True


def test_lister_obsoletes_filtre_domaine(client, db_session, validator, auth_header):
    _, it = seed_ticket_reponse(db_session, statut="VALIDÉE", domaine="IT")
    _, rh = seed_ticket_reponse(db_session, statut="VALIDÉE", domaine="RH")
    _rendre_obsolete(db_session, it)
    _rendre_obsolete(db_session, rh)

    body = client.get(f"{API}/reponses/obsoletes", params={"domaine": "IT"}, headers=auth_header(validator)).json()

    assert [i["reponse_id"] for i in body["items"]] == [str(it.id)]


def test_restaurer_leve_le_drapeau_et_reindexe(client, db_session, validator, auth_header, mock_side_effects):
    _, reponse = seed_ticket_reponse(db_session, statut="VALIDÉE", canonique=True, nb_validations=3)
    _rendre_obsolete(db_session, reponse)

    resp = client.post(f"{API}/reponses/{reponse.id}/restaurer", headers=auth_header(validator))

    assert resp.status_code == 200
    db_session.expunge_all()
    restauree = db_session.get(Reponse, reponse.id)
    assert restauree.obsolete is False
    assert restauree.obsolete_raison is None
    assert restauree.obsolete_doc_id is None
    assert restauree.obsolete_at is None
    # Les validations acquises ne sont pas remises en cause par le cycle
    assert restauree.nb_validations == 3
    assert mock_side_effects.feedback.called


def test_restaurer_remonte_toute_la_famille(client, db_session, validator, auth_header, mock_side_effects):
    """`marquer_obsoletes` a retiré les points de la source ET de ses copies :
    la restauration doit être symétrique, sinon les copies restent muettes."""
    _, source = seed_ticket_reponse(db_session, statut="VALIDÉE", canonique=True)
    _, copie = seed_ticket_reponse(db_session, statut="VALIDÉE", reponse_source_id=source.id)
    _rendre_obsolete(db_session, source)
    _rendre_obsolete(db_session, copie)
    copie_id = copie.id

    resp = client.post(f"{API}/reponses/{source.id}/restaurer", headers=auth_header(validator))

    assert resp.json()["nb_restaurees"] == 2
    db_session.expunge_all()
    assert db_session.get(Reponse, copie_id).obsolete is False


def test_restaurer_non_obsolete_renvoie_409(client, db_session, validator, auth_header):
    _, reponse = seed_ticket_reponse(db_session, statut="VALIDÉE", canonique=True)

    resp = client.post(f"{API}/reponses/{reponse.id}/restaurer", headers=auth_header(validator))

    assert resp.status_code == 409


def test_restaurer_hors_domaine_renvoie_403(client, db_session, validator, auth_header):
    _, reponse = seed_ticket_reponse(db_session, statut="VALIDÉE", domaine="RH")
    _rendre_obsolete(db_session, reponse)

    resp = client.post(f"{API}/reponses/{reponse.id}/restaurer", headers=auth_header(validator))

    assert resp.status_code == 403


def test_supprimer_obsolete_non_canonique_autorise(client, db_session, validator, auth_header):
    """L'onglet Obsolètes doit pouvoir purger une réponse jamais devenue canonique."""
    _, reponse = seed_ticket_reponse(db_session, statut="VALIDÉE", canonique=False)
    _rendre_obsolete(db_session, reponse)

    resp = client.delete(f"{API}/reponses/{reponse.id}", headers=auth_header(validator))

    assert resp.status_code == 200
    db_session.expunge_all()
    assert db_session.get(Reponse, reponse.id) is None


def test_supprimer_remet_a_zero_l_obsolescence_des_copies(client, db_session, validator, auth_header):
    """Détachée mais toujours marquée, la copie resterait à jamais dans l'onglet
    Obsolètes — ou dans l'onglet À relire — sans plus aucune source pour l'en
    sortir : les deux listes ne montrent que les sources."""
    _, source = seed_ticket_reponse(db_session, statut="VALIDÉE", canonique=True)
    _, copie = seed_ticket_reponse(db_session, statut="VALIDÉE", reponse_source_id=source.id)
    _rendre_obsolete(db_session, source)
    _rendre_obsolete(db_session, copie)
    _signaler(db_session, copie)
    copie_id = copie.id

    client.delete(f"{API}/reponses/{source.id}", headers=auth_header(validator))

    db_session.expunge_all()
    detachee = db_session.get(Reponse, copie_id)
    assert detachee.obsolete is False
    assert detachee.obsolete_doc_id is None
    assert detachee.a_relire is False
    assert detachee.a_relire_doc_id is None
    assert detachee.a_relire_version is None
    assert detachee.a_relire_raison is None
    assert detachee.a_relire_at is None


# --------------------------------------------------------------------------- #
# À relire : GET /reponses/a-relire, confirmer-actualite, retirer
# --------------------------------------------------------------------------- #
def _signaler(db, reponse, *, doc_id="doc-modifie", raison="DOC_MODIFIÉ", version=3):
    reponse.a_relire = True
    reponse.a_relire_raison = raison
    reponse.a_relire_doc_id = doc_id
    reponse.a_relire_version = version
    reponse.a_relire_at = datetime.now(timezone.utc)
    db.commit()
    return reponse


def test_lister_a_relire(client, db_session, validator, auth_header):
    _, signalee = seed_ticket_reponse(db_session, statut="VALIDÉE", canonique=True, nb_validations=4)
    _signaler(db_session, signalee)
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
        _signaler(db_session, r, doc_id="charte-rh")
    _, autre = seed_ticket_reponse(db_session, statut="VALIDÉE", canonique=True)
    _signaler(db_session, autre, doc_id="reglement-it")

    body = client.get(f"{API}/reponses/a-relire", headers=auth_header(validator)).json()

    assert body["total"] == 4
    assert body["nb_documents"] == 2


def test_lister_a_relire_remonte_les_changements(client, db_session, validator, auth_header):
    """Sans les extraits, « cette réponse est liée à Charte_RH v3 » ne permet de
    juger de rien : c'est le diff qu'on relit, pas le numéro de version."""
    from app.models.document import Document
    from app.models.document_version import DocumentVersion

    db_session.add(Document(doc_id="charte-rh", filename="charte.md", domaine="IT", version=3))
    db_session.add(DocumentVersion(
        doc_id="charte-rh", version=3, filename="charte.md",
        changements={"nb_ajoutes": 1, "nb_retires": 0,
                     "extraits_ajoutes": ["Article 7 bis…"], "extraits_retires": []},
    ))
    _, reponse = seed_ticket_reponse(db_session, statut="VALIDÉE", canonique=True)
    _signaler(db_session, reponse, doc_id="charte-rh", version=3)

    item = client.get(f"{API}/reponses/a-relire", headers=auth_header(validator)).json()["items"][0]

    assert item["document_filename"] == "charte.md"
    assert item["document_supprime"] is False
    assert item["changements"]["extraits_ajoutes"] == ["Article 7 bis…"]


def test_lister_a_relire_masque_les_copies(client, db_session, validator, auth_header):
    _, source = seed_ticket_reponse(db_session, statut="VALIDÉE", canonique=True)
    _, copie = seed_ticket_reponse(db_session, statut="VALIDÉE", reponse_source_id=source.id)
    _signaler(db_session, source)
    _signaler(db_session, copie)

    body = client.get(f"{API}/reponses/a-relire", headers=auth_header(validator)).json()

    assert [i["reponse_id"] for i in body["items"]] == [str(source.id)]


def test_lister_a_relire_filtre_domaine(client, db_session, validator, auth_header):
    _, it = seed_ticket_reponse(db_session, statut="VALIDÉE", domaine="IT")
    _, rh = seed_ticket_reponse(db_session, statut="VALIDÉE", domaine="RH")
    _signaler(db_session, it)
    _signaler(db_session, rh)

    body = client.get(f"{API}/reponses/a-relire", params={"domaine": "IT"}, headers=auth_header(validator)).json()

    assert [i["reponse_id"] for i in body["items"]] == [str(it.id)]


def test_confirmer_actualite_leve_le_signalement(client, db_session, validator, auth_header):
    _, reponse = seed_ticket_reponse(db_session, statut="VALIDÉE", canonique=True, nb_validations=3)
    _signaler(db_session, reponse)

    resp = client.post(f"{API}/reponses/{reponse.id}/confirmer-actualite", headers=auth_header(validator))

    assert resp.status_code == 200
    db_session.expunge_all()
    confirmee = db_session.get(Reponse, reponse.id)
    assert confirmee.a_relire is False
    assert confirmee.a_relire_doc_id is None
    # Rien d'autre ne change : la réponse n'a jamais cessé d'être servie.
    assert confirmee.obsolete is False
    assert confirmee.nb_validations == 3


def test_confirmer_actualite_remonte_toute_la_famille(client, db_session, validator, auth_header):
    """Le drapeau a été posé sur la famille entière : le lever sur la seule source
    laisserait les copies signalées, sans aucune issue puisque la liste ne montre
    que les sources."""
    _, source = seed_ticket_reponse(db_session, statut="VALIDÉE", canonique=True)
    _, copie = seed_ticket_reponse(db_session, statut="VALIDÉE", reponse_source_id=source.id)
    _signaler(db_session, source)
    _signaler(db_session, copie)
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
    _signaler(db_session, reponse)

    resp = client.post(f"{API}/reponses/{reponse.id}/confirmer-actualite", headers=auth_header(validator))

    assert resp.status_code == 403


def test_confirmer_actualite_en_lot(client, db_session, validator, auth_header):
    """La sortie normale quand un document en a signalé des dizaines : on lit le
    diff une fois, on juge l'ensemble ensuite."""
    ids = []
    for _ in range(3):
        _, r = seed_ticket_reponse(db_session, statut="VALIDÉE", canonique=True)
        _signaler(db_session, r, doc_id="charte-rh", version=3)
        ids.append(r.id)
    _, autre_doc = seed_ticket_reponse(db_session, statut="VALIDÉE", canonique=True)
    _signaler(db_session, autre_doc, doc_id="reglement-it", version=1)
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
    # Le lot est borné au document visé.
    assert db_session.get(Reponse, autre_id).a_relire is True


def test_confirmer_actualite_en_lot_borne_a_la_version(client, db_session, validator, auth_header):
    """Un document remis à jour entre-temps a reflagué sur v4 : une confirmation
    partie de l'écran de v3 ne doit pas balayer un signalement jamais vu."""
    _, v3 = seed_ticket_reponse(db_session, statut="VALIDÉE", canonique=True)
    _, v4 = seed_ticket_reponse(db_session, statut="VALIDÉE", canonique=True)
    _signaler(db_session, v3, doc_id="charte-rh", version=3)
    _signaler(db_session, v4, doc_id="charte-rh", version=4)
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
    _, it = seed_ticket_reponse(db_session, statut="VALIDÉE", domaine="IT")
    _, rh = seed_ticket_reponse(db_session, statut="VALIDÉE", domaine="RH")
    _signaler(db_session, it, doc_id="charte-rh", version=3)
    _signaler(db_session, rh, doc_id="charte-rh", version=3)
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
    _, reponse = seed_ticket_reponse(db_session, statut="VALIDÉE", canonique=True)
    _signaler(db_session, reponse, doc_id="charte-rh", version=3)

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
    _, reponse = seed_ticket_reponse(db_session, statut="VALIDÉE", canonique=True)
    _signaler(db_session, reponse, doc_id="charte-rh", version=3)

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
    _signaler(db_session, reponse)

    resp = client.post(f"{API}/reponses/{reponse.id}/retirer", headers=auth_header(validator))

    assert resp.status_code == 403


def test_editer_signalee_non_canonique_autorise(client, db_session, validator, auth_header, mock_side_effects):
    """« Corriger » est l'une des trois issues du signalement : la refuser aux
    VALIDÉE pas encore promues ne laisserait que confirmer ou retirer."""
    _, reponse = seed_ticket_reponse(db_session, statut="VALIDÉE", canonique=False)
    _signaler(db_session, reponse)

    resp = client.put(
        f"{API}/reponses/{reponse.id}/editer",
        json={"contenu": "Texte remis à jour"},
        headers=auth_header(validator),
    )

    assert resp.status_code == 200
    db_session.expunge_all()
    editee = db_session.get(Reponse, reponse.id)
    # Réécrire la réponse *est* la relecture qu'on demandait.
    assert editee.a_relire is False
    assert editee.contenu_corrige == "Texte remis à jour"


def test_restaurer_leve_aussi_le_signalement(client, db_session, validator, auth_header, mock_side_effects):
    """Restaurer *est* le jugement humain que le signalement réclamait : le
    reposer renverrait aussitôt la réponse dans l'onglet À relire."""
    _, reponse = seed_ticket_reponse(db_session, statut="VALIDÉE", canonique=True)
    _rendre_obsolete(db_session, reponse)
    _signaler(db_session, reponse)

    client.post(f"{API}/reponses/{reponse.id}/restaurer", headers=auth_header(validator))

    db_session.expunge_all()
    restauree = db_session.get(Reponse, reponse.id)
    assert restauree.obsolete is False
    assert restauree.a_relire is False


def test_corriger_leve_le_signalement(client, db_session, validator, auth_header, mock_side_effects):
    """`reponses_obsoletes` ne retient que les VALIDÉE : une réponse signalée puis
    corrigée sortirait du périmètre en gardant son drapeau, et occuperait l'onglet
    sans qu'aucune action ne l'en déloge."""
    _, reponse = seed_ticket_reponse(db_session, statut="EN_ATTENTE")
    _signaler(db_session, reponse)

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
