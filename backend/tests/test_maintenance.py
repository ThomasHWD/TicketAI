"""Tests pour le mode maintenance.

Unitaires :
  - _CONFIG_DEFAULTS inclut la clé maintenance
  - invalidate_maintenance_cache() remet checked_at à zéro
  - GET /public/maintenance sans token → 200 défaut
  - Routes exemptées passent quand le cache est forcé active

Intégration (@pytest.mark.integration — nécessite Postgres réel) :
  - Maintenance inactive → route normale
  - Maintenance active + sans token → 503
  - Maintenance active + token user → 503
  - Maintenance active + token admin → 200 (passthrough)
  - /health exempté pendant maintenance
  - /api/v1/auth/login exempté pendant maintenance
  - /api/v1/public/maintenance exempté pendant maintenance
  - PUT /admin/config/maintenance invalide le cache
"""

import time
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


@pytest.fixture(autouse=True)
def reset_cache():
    """Remet le cache maintenance à l'état inactif avant chaque test."""
    from app.middleware.maintenance import _cache, invalidate_maintenance_cache

    _cache["active"] = False
    _cache["message"] = ""
    invalidate_maintenance_cache()
    yield
    _cache["active"] = False
    _cache["message"] = ""
    invalidate_maintenance_cache()


# ──────────────────────────────────────────────────────────────────────────────
# Unitaires
# ──────────────────────────────────────────────────────────────────────────────


def test_config_defaults_inclut_maintenance():
    from app.services.admin_service import _CONFIG_DEFAULTS

    assert "maintenance" in _CONFIG_DEFAULTS
    assert _CONFIG_DEFAULTS["maintenance"] == {"active": False, "message": ""}


def test_invalidate_maintenance_cache():
    from app.middleware.maintenance import _cache, invalidate_maintenance_cache

    _cache["checked_at"] = time.monotonic()
    assert _cache["checked_at"] > 0
    invalidate_maintenance_cache()
    assert _cache["checked_at"] == 0.0


def test_public_maintenance_sans_token_retourne_defaut(client):
    r = client.get(f"{API}/public/maintenance")
    assert r.status_code == 200
    data = r.json()
    assert data["active"] is False
    assert "message" in data


def test_health_exempte_cache_actif(client):
    from app.middleware.maintenance import _cache

    _cache["active"] = True
    _cache["checked_at"] = time.monotonic() + 3600  # cache chaud
    r = client.get("/health")
    assert r.status_code == 200


def test_public_maintenance_exempte_cache_actif(client):
    from app.middleware.maintenance import _cache

    _cache["active"] = True
    _cache["checked_at"] = time.monotonic() + 3600
    r = client.get(f"{API}/public/maintenance")
    assert r.status_code == 200


@pytest.mark.parametrize("path", [
    "/api/v1/auth/login",
    "/api/v1/admin/health",
])
def test_chemins_exempts_cache_actif(client, path):
    from app.middleware.maintenance import _cache

    _cache["active"] = True
    _cache["checked_at"] = time.monotonic() + 3600
    r = client.get(path)
    # Ces routes peuvent retourner autre chose que 200 (401, 422…)
    # mais jamais 503 puisqu'elles sont exemptées
    assert r.status_code != 503


def test_non_admin_bloque_cache_actif(client):
    from app.middleware.maintenance import _cache

    _cache["active"] = True
    _cache["checked_at"] = time.monotonic() + 3600
    r = client.get(f"{API}/tickets")
    assert r.status_code == 503
    body = r.json()
    assert body["detail"] == "Service en maintenance"


def test_token_invalide_pendant_maintenance_503(client):
    from app.middleware.maintenance import _cache

    _cache["active"] = True
    _cache["checked_at"] = time.monotonic() + 3600
    r = client.get(f"{API}/tickets", headers={"Authorization": "Bearer jeton_invalide"})
    assert r.status_code == 503


# ──────────────────────────────────────────────────────────────────────────────
# Intégration
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.integration
def test_maintenance_inactive_route_normale(client, auth_headers):
    r = client.get(f"{API}/tickets", headers=auth_headers)
    # 200 ou autre code métier — pas 503
    assert r.status_code != 503


@pytest.mark.integration
def test_maintenance_active_sans_token_503(client, db_session, admin_headers):
    client.put(
        f"{API}/admin/config/maintenance",
        json={"value": {"active": True, "message": "Travaux"}},
        headers=admin_headers,
    )
    r = client.get(f"{API}/tickets")
    assert r.status_code == 503
    assert r.json()["message"] == "Travaux"


@pytest.mark.integration
def test_maintenance_active_token_user_503(client, db_session, admin_headers, user_factory, auth_header):
    client.put(
        f"{API}/admin/config/maintenance",
        json={"value": {"active": True, "message": ""}},
        headers=admin_headers,
    )
    user_headers = auth_header(user_factory("USER"))
    r = client.get(f"{API}/tickets", headers=user_headers)
    assert r.status_code == 503


@pytest.mark.integration
def test_maintenance_active_token_admin_passe(client, db_session, admin_headers):
    client.put(
        f"{API}/admin/config/maintenance",
        json={"value": {"active": True, "message": ""}},
        headers=admin_headers,
    )
    r = client.get(f"{API}/tickets", headers=admin_headers)
    assert r.status_code != 503


@pytest.mark.integration
def test_get_public_maintenance_reflète_db(client, db_session, admin_headers):
    client.put(
        f"{API}/admin/config/maintenance",
        json={"value": {"active": True, "message": "Test DB"}},
        headers=admin_headers,
    )
    r = client.get(f"{API}/public/maintenance")
    assert r.status_code == 200
    data = r.json()
    assert data["active"] is True
    assert data["message"] == "Test DB"


@pytest.mark.integration
def test_put_maintenance_invalide_cache(client, db_session, admin_headers):
    from app.middleware.maintenance import _cache

    # On chauffe le cache avec maintenance inactive
    _cache["active"] = False
    _cache["checked_at"] = time.monotonic() + 3600

    # PUT invalide le cache
    client.put(
        f"{API}/admin/config/maintenance",
        json={"value": {"active": True, "message": ""}},
        headers=admin_headers,
    )

    # Après invalidation, checked_at est à zéro → prochain appel relit la DB
    assert _cache["checked_at"] == 0.0

    # La prochaine requête doit lire la DB et retourner 503
    r = client.get(f"{API}/tickets")
    assert r.status_code == 503
