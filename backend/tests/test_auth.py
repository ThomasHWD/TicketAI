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


# --------------------------------------------------------------------------- #
# Limiteur de login par compte (unitaire, Valkey simulé)
# --------------------------------------------------------------------------- #
class _ValkeyEnMemoire:
    def __init__(self):
        self.valeurs = {}

    def incr(self, cle):
        self.valeurs[cle] = self.valeurs.get(cle, 0) + 1
        return self.valeurs[cle]

    def get(self, cle):
        return self.valeurs.get(cle)

    def delete(self, cle):
        self.valeurs.pop(cle, None)

    def expire(self, *_a, **_k):
        pass

    def ttl(self, _cle):
        return 60


@pytest.fixture
def valkey(monkeypatch):
    import app.api.v1.auth as auth

    faux = _ValkeyEnMemoire()
    monkeypatch.setattr(auth.redis_lib, "from_url", lambda *_a, **_k: faux)
    return faux


def test_login_bloque_un_compte_apres_trop_d_echecs(client, valkey, monkeypatch):
    """Per account, whatever the IP: 10 failures on alice, then even the right password waits — bob does not."""
    appels = []
    monkeypatch.setattr(ldap_auth, "authenticate", lambda u, _p: appels.append(u))
    valkey.valeurs["rate:login:compte:alice"] = 10

    assert client.post(f"{API}/auth/login", data={"username": "Alice", "password": "x"}).status_code == 429
    assert client.post(f"{API}/auth/login", data={"username": "bob", "password": "x"}).status_code == 401
    assert appels == ["bob"]
    assert valkey.valeurs["rate:login:compte:bob"] == 1


# --------------------------------------------------------------------------- #
# Rôles LDAP : égalité de groupe, jamais sous-chaîne
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("groupe", "member_of", "attendu"),
    [
        ("PORTAIL-TICKETING-ADM", ["CN=PORTAIL-TICKETING-ADM,OU=G,DC=onacvg,DC=fr"], True),
        ("PORTAIL-TICKETING-ADM", ["CN=PORTAIL-TICKETING-ADM-LECTURE,OU=G,DC=onacvg,DC=fr"], False),
        ("PORTAIL-TICKETING-ADM", ["CN=X,OU=PORTAIL-TICKETING-ADM,DC=onacvg,DC=fr"], False),
        ("CN=TicketAI-Admins, OU=G,DC=x", ["cn=ticketai-admins,ou=g,dc=x"], True),
        ("CN=TicketAI-Admins,OU=G,DC=x", ["CN=TicketAI-Admins,OU=G,DC=x,DC=y"], False),
        ("", ["CN=Tout-le-monde,DC=x"], False),
    ],
)
def test_membre_du_groupe(groupe, member_of, attendu):
    assert ldap_auth.membre_du_groupe(groupe, member_of) is attendu


def test_groupe_ldap_vide_refuse_au_demarrage():
    from app.config import Settings, settings

    with pytest.raises(ValueError, match="LDAP_GROUP_ADMIN"):
        Settings(**{**settings.model_dump(), "ldap_server_url": "ldaps://ad:636", "ldap_group_admin": ""})
