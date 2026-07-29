"""Tests pour la configuration du site (/api/v1/admin/config) et l'ajout de
membre par email (provisionnement JIT).

Unitaires (sans infra) :
  - Forme des valeurs par défaut (_CONFIG_DEFAULTS)
  - PUT /config protégé (403 non-admin, 401 sans token)

Intégration (@pytest.mark.integration — nécessite Postgres réel) :
  - GET /config renvoie les défauts quand la table est vide
  - PUT /config/{key} crée puis met à jour une clé, GET reflète la valeur
  - PUT /config/{key} inconnue → 404
  - Ajout d'un membre existant via son email (branche sans LDAP) → 201
  - Ajout via un identifiant non-UUID / introuvable → 404
"""

import uuid

import pytest

API = "/api/v1"


# ──────────────────────────────────────────────────────────────────────────────
# Fixtures locales
# ──────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def admin_headers(db_session, auth_header):
    from app.models.user import User

    u = User(email=f"{uuid.uuid4()}@test.local", role="ADMIN")
    db_session.add(u)
    db_session.commit()
    db_session.refresh(u)
    return auth_header(u)


@pytest.fixture
def groupe_factory(db_session):
    from app.models.groupe import Groupe

    def _make(nom: str = "Groupe Test", domaine: str = None):
        d = domaine or str(uuid.uuid4())[:8].upper()
        g = Groupe(nom=nom, domaine=d)
        db_session.add(g)
        db_session.commit()
        db_session.refresh(g)
        return g

    return _make


# ──────────────────────────────────────────────────────────────────────────────
# Unitaires
# ──────────────────────────────────────────────────────────────────────────────


def test_config_defaults_shape():
    from app.api.v1.admin import _CONFIG_DEFAULTS

    assert "banner" in _CONFIG_DEFAULTS
    banner = _CONFIG_DEFAULTS["banner"]
    assert banner == {"active": False, "message": "", "url": ""}


def test_set_config_refuse_non_admin(client, user_factory, auth_header):
    headers = auth_header(user_factory("USER"))
    r = client.put(
        f"{API}/admin/config/banner",
        json={"value": {"active": True, "message": "x", "url": ""}},
        headers=headers,
    )
    assert r.status_code == 403


def test_set_config_refuse_sans_token(client):
    r = client.put(f"{API}/admin/config/banner", json={"value": {}})
    assert r.status_code == 401


# ──────────────────────────────────────────────────────────────────────────────
# Intégration
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.integration
def test_get_config_renvoie_defauts(client, auth_headers):
    r = client.get(f"{API}/admin/config", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["banner"] == {"active": False, "message": "", "url": ""}


@pytest.mark.integration
def test_set_config_cree_puis_maj(client, admin_headers):
    payload = {"active": True, "message": "Maintenance", "url": "https://x.test"}
    r = client.put(f"{API}/admin/config/banner", json={"value": payload}, headers=admin_headers)
    assert r.status_code == 200
    assert r.json() == {"key": "banner", "value": payload}

    # GET reflète la valeur persistée
    r = client.get(f"{API}/admin/config", headers=admin_headers)
    assert r.json()["banner"] == payload

    # Mise à jour idempotente sur la même clé (pas de doublon)
    payload2 = {"active": False, "message": "", "url": ""}
    r = client.put(f"{API}/admin/config/banner", json={"value": payload2}, headers=admin_headers)
    assert r.status_code == 200
    assert client.get(f"{API}/admin/config", headers=admin_headers).json()["banner"] == payload2


@pytest.mark.integration
def test_set_config_cle_inconnue_404(client, admin_headers):
    r = client.put(f"{API}/admin/config/inconnue", json={"value": 1}, headers=admin_headers)
    assert r.status_code == 404


@pytest.mark.integration
def test_add_membre_par_email(client, admin_headers, groupe_factory, db_session):
    from app.models.user import User

    g = groupe_factory()
    u = User(email=f"{uuid.uuid4()}@test.local", role="USER", is_gestionnaire=True)
    db_session.add(u)
    db_session.commit()
    db_session.refresh(u)

    r = client.post(f"{API}/admin/groupes/{g.id}/membres/{u.email}", headers=admin_headers)
    assert r.status_code == 201
    assert any(m["email"] == u.email for m in r.json()["membres"])


@pytest.mark.integration
def test_add_membre_identifiant_invalide_404(client, admin_headers, groupe_factory):
    g = groupe_factory()
    r = client.post(f"{API}/admin/groupes/{g.id}/membres/pas-un-uuid", headers=admin_headers)
    assert r.status_code == 404
