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
    """Un validateur réellement présent en base. Son JWT sert d'identité pour les
    routes de validation (`reponses.validator_id` est une FK vers `users.id`)."""
    user = make_user(db_session)
    db_session.commit()
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
    _, reponse = seed_ticket_reponse(
        db_session, nb_validations=settings.seuil_canonique - 1
    )

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


def test_valider_incremente_la_source_pas_la_copie(
    client, db_session, validator, auth_header
):
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


def test_valider_reponse_source_declenche_reindexation(
    client, db_session, validator, auth_header, mock_side_effects
):
    _, reponse = seed_ticket_reponse(db_session)

    client.post(
        f"{API}/reponses/{reponse.id}/valider",
        headers=auth_header(validator),
    )

    # feedback_job.apply_async doit être appelé pour réindexer dans Qdrant.
    assert mock_side_effects.feedback.called


def test_valider_etat_final_renvoie_409(client, db_session, auth_headers):
    _, reponse = seed_ticket_reponse(db_session, statut="REJETÉE")

    resp = client.post(
        f"{API}/reponses/{reponse.id}/valider",
        headers=auth_headers,
    )

    assert resp.status_code == 409


def test_valider_auto_validation_renvoie_403(client, db_session, auth_header):
    user = make_user(db_session)
    db_session.commit()
    _, reponse = seed_ticket_reponse(db_session, user_id=user.id)

    # L'utilisateur connecté est le créateur du ticket → interdit de se valider.
    resp = client.post(
        f"{API}/reponses/{reponse.id}/valider",
        headers=auth_header(user),
    )

    assert resp.status_code == 403


def test_valider_ticket_verrouille_par_autre_renvoie_409(
    client, db_session, validator, auth_header
):
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


def test_valider_introuvable_renvoie_404(client, db_session, auth_headers):
    resp = client.post(
        f"{API}/reponses/{uuid.uuid4()}/valider",
        headers=auth_headers,
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


def test_corriger_contenu_vide_renvoie_400(client, db_session, auth_headers):
    _, reponse = seed_ticket_reponse(db_session)

    resp = client.put(
        f"{API}/reponses/{reponse.id}/corriger",
        json={"contenu_corrige": "   "},
        headers=auth_headers,
    )

    assert resp.status_code == 400


# --------------------------------------------------------------------------- #
# PUT /reponses/{id}/editer  (réponses canoniques — réservé ADMIN)
# --------------------------------------------------------------------------- #
def test_editer_non_admin_renvoie_403(client, db_session, auth_headers):
    _, reponse = seed_ticket_reponse(db_session, statut="VALIDÉE", canonique=True)

    resp = client.put(
        f"{API}/reponses/{reponse.id}/editer",
        json={"contenu": "Nouveau contenu servi"},
        headers=auth_headers,  # rôle USER
    )

    assert resp.status_code == 403


def test_editer_canonique_ok(client, db_session, user_factory, auth_header):
    admin = user_factory("ADMIN")
    _, reponse = seed_ticket_reponse(db_session, statut="VALIDÉE", canonique=True)

    resp = client.put(
        f"{API}/reponses/{reponse.id}/editer",
        json={"contenu": "Nouveau contenu servi"},
        headers=auth_header(admin),
    )

    assert resp.status_code == 200
    db_session.expire_all()
    assert db_session.get(Reponse, reponse.id).contenu_corrige == "Nouveau contenu servi"


def test_editer_non_canonique_renvoie_409(client, db_session, user_factory, auth_header):
    admin = user_factory("ADMIN")
    _, reponse = seed_ticket_reponse(db_session, canonique=False)

    resp = client.put(
        f"{API}/reponses/{reponse.id}/editer",
        json={"contenu": "Peu importe"},
        headers=auth_header(admin),
    )

    assert resp.status_code == 409


def test_editer_contenu_vide_renvoie_400(client, db_session, user_factory, auth_header):
    admin = user_factory("ADMIN")
    _, reponse = seed_ticket_reponse(db_session, statut="VALIDÉE", canonique=True)

    resp = client.put(
        f"{API}/reponses/{reponse.id}/editer",
        json={"contenu": "  "},
        headers=auth_header(admin),
    )

    assert resp.status_code == 400


# --------------------------------------------------------------------------- #
# DELETE /reponses/{id}  (réponses canoniques — réservé ADMIN)
# --------------------------------------------------------------------------- #
def test_supprimer_non_canonique_renvoie_409(
    client, db_session, user_factory, auth_header
):
    admin = user_factory("ADMIN")
    _, reponse = seed_ticket_reponse(db_session, canonique=False)

    resp = client.delete(
        f"{API}/reponses/{reponse.id}", headers=auth_header(admin)
    )

    assert resp.status_code == 409


def test_supprimer_canonique_detache_les_copies(
    client, db_session, user_factory, auth_header, mock_side_effects
):
    admin = user_factory("ADMIN")
    _, source = seed_ticket_reponse(db_session, statut="VALIDÉE", canonique=True)
    _, copie = seed_ticket_reponse(
        db_session, statut="VALIDÉE", canonique=True, reponse_source_id=source.id
    )

    resp = client.delete(
        f"{API}/reponses/{source.id}", headers=auth_header(admin)
    )

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


def test_supprimer_canonique_nettoie_les_chunks(
    client, db_session, user_factory, auth_header
):
    admin = user_factory("ADMIN")
    _, reponse = seed_ticket_reponse(db_session, statut="VALIDÉE", canonique=True)
    db_session.add(
        ReponseChunk(reponse_id=reponse.id, doc_id="doc-1", chunk_index=0)
    )
    db_session.commit()

    reponse_id = reponse.id
    resp = client.delete(
        f"{API}/reponses/{reponse_id}", headers=auth_header(admin)
    )

    assert resp.status_code == 200
    db_session.expunge_all()
    remaining = (
        db_session.query(ReponseChunk)
        .filter(ReponseChunk.reponse_id == reponse_id)
        .count()
    )
    assert remaining == 0


# --------------------------------------------------------------------------- #
# GET /reponses/en-attente  et  /reponses/canoniques
# --------------------------------------------------------------------------- #
def test_lister_en_attente_filtre_domaine(client, db_session, auth_headers):
    seed_ticket_reponse(db_session, domaine="IT")
    seed_ticket_reponse(db_session, domaine="RH")

    resp = client.get(
        f"{API}/reponses/en-attente", params={"domaine": "IT"}, headers=auth_headers
    )

    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 1
    assert items[0]["domaine"] == "IT"
    assert {"reponse_id", "ticket_id", "question", "reponse"} <= items[0].keys()


def test_lister_canoniques_pagination(client, db_session, auth_headers):
    # Une source canonique visible + une copie (source renseignée) qui ne doit PAS
    # apparaître dans la liste.
    _, source = seed_ticket_reponse(
        db_session, statut="VALIDÉE", canonique=True, nb_validations=3
    )
    seed_ticket_reponse(
        db_session, statut="VALIDÉE", canonique=True, reponse_source_id=source.id
    )

    resp = client.get(
        f"{API}/reponses/canoniques",
        params={"page": 1, "limit": 20},
        headers=auth_headers,
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["page"] == 1
    assert len(body["items"]) == 1
    assert body["items"][0]["reponse_id"] == str(source.id)
