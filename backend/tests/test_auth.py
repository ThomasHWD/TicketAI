"""Tests de l'authentification LDAP/JWT.

- Unitaires (sans infra) : émission/décodage JWT, garde-fou identifiants vides.
- Intégration (base requise) : provisioning JIT ``get_or_create_user`` et les
  routes ``/auth`` (login en échec, ``/me``, protection des documents).
"""

import uuid

import pytest
from app.services import ldap_auth

API = "/api/v1"


# --------------------------------------------------------------------------- #
# JWT (unitaire)
# --------------------------------------------------------------------------- #
def test_create_et_decode_token_roundtrip():
    from app.core.security import create_access_token, decode_token

    uid = uuid.uuid4()
    token = create_access_token(uid, "ADMIN")
    payload = decode_token(token)

    assert payload["sub"] == str(uid)
    assert payload["role"] == "ADMIN"
    assert "exp" in payload


def test_decode_token_invalide_leve():
    from app.core.security import decode_token
    from jose import JWTError

    with pytest.raises(JWTError):
        decode_token("pas-un-vrai-jwt")


# --------------------------------------------------------------------------- #
# authenticate (unitaire)
# --------------------------------------------------------------------------- #
def test_authenticate_identifiants_vides():
    # Court-circuit avant tout appel réseau : identifiants vides → None.
    assert ldap_auth.authenticate("", "") is None
    assert ldap_auth.authenticate("thomas", "") is None
    assert ldap_auth.authenticate("", "password") is None


# --------------------------------------------------------------------------- #
# Provisioning JIT + route de login (intégration)
# --------------------------------------------------------------------------- #
@pytest.mark.integration
def test_get_or_create_user_cree_puis_idempotent(db_session):
    from app.api.v1.auth import get_or_create_user
    from app.models.user import User
    from app.services.ldap_auth import LdapIdentity

    identity = LdapIdentity(
        username="alice",
        email="alice.martin@ticketai.local",
        prenom="Alice",
        nom="Martin",
        departement=None,
        is_gestionnaire=False,
    )

    user = get_or_create_user(db_session, identity)
    assert user.role == "USER"
    assert user.email == "alice.martin@ticketai.local"
    first_id = user.id

    # Deuxième login : pas de doublon, mise à jour des attributs.
    again = get_or_create_user(db_session, identity)
    assert again.id == first_id
    assert db_session.query(User).filter(User.email == identity.email).count() == 1


@pytest.mark.integration
def test_login_route_mauvais_identifiants_renvoie_401(client, db_session):
    resp = client.post(
        f"{API}/auth/login",
        data={"username": "bob", "password": "faux"},
    )
    assert resp.status_code == 401


@pytest.mark.integration
def test_me_route_renvoie_profil(client, db_session, user_factory, auth_header):
    user = user_factory("USER")
    resp = client.get(f"{API}/auth/me", headers=auth_header(user))
    assert resp.status_code == 200
    assert resp.json()["id"] == str(user.id)


def test_me_route_sans_token_renvoie_401(client):
    resp = client.get(f"{API}/auth/me")
    assert resp.status_code == 401


# --------------------------------------------------------------------------- #
# Protection des endpoints documents
# --------------------------------------------------------------------------- #
def test_documents_sans_token_renvoie_401(client):
    resp = client.get(f"{API}/documents")
    assert resp.status_code == 401


@pytest.mark.integration
def test_documents_delete_reserve_admin(client, db_session, user_factory, auth_header):
    # require_admin s'exécute avant le corps → 403 pour un simple USER.
    user = user_factory("USER")
    resp = client.delete(f"{API}/documents/{uuid.uuid4()}", headers=auth_header(user))
    assert resp.status_code == 403
