"""Tests pour les endpoints /api/v1/admin (groupes, membres, chef, gestionnaires).

Unitaires (sans infra) :
  - Sérialisation des helpers (_serialize_groupe, _serialize_user_summary)
  - Refus 403 si l'utilisateur n'est pas ADMIN

Intégration (@pytest.mark.integration — nécessite Postgres réel) :
  - CRUD complet sur les groupes
  - Ajout / suppression de membres
  - Promotion / rétrogradation chef
  - Liste gestionnaires
  - Contrainte d'unicité domaine
"""

import uuid

import pytest

API = "/api/v1"


# ──────────────────────────────────────────────────────────────────────────────
# Fixtures locales
# ──────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def admin_factory(db_session):
    from app.models.user import User

    def _make(is_gestionnaire: bool = False):
        u = User(
            email=f"{uuid.uuid4()}@test.local",
            role="ADMIN",
            is_gestionnaire=is_gestionnaire,
        )
        db_session.add(u)
        db_session.commit()
        db_session.refresh(u)
        return u

    return _make


@pytest.fixture
def admin_headers(admin_factory, auth_header):
    return auth_header(admin_factory())


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
# Unitaires — helpers de sérialisation
# ──────────────────────────────────────────────────────────────────────────────


def test_serialize_user_summary_fields():
    from unittest.mock import MagicMock

    from app.services.admin_service import serialize_user_summary as _serialize_user_summary

    user = MagicMock()
    user.id = uuid.uuid4()
    user.email = "a@b.com"
    user.prenom = "Alice"
    user.nom = "Durand"
    user.role = "USER"
    user.departement = "IT"
    user.is_gestionnaire = False
    user.groupes = []

    result = _serialize_user_summary(user)
    assert result["email"] == "a@b.com"
    assert result["role"] == "USER"
    assert result["groupes"] == []


def test_serialize_groupe_base_fields():
    from unittest.mock import MagicMock

    from app.services.admin_service import serialize_groupe as _serialize_groupe

    g = MagicMock()
    g.id = uuid.uuid4()
    g.nom = "Mon groupe"
    g.domaine = "RH"
    g.created_at = None
    g.membres = []

    result = _serialize_groupe(g, include_membres=False)
    assert result["nom"] == "Mon groupe"
    assert result["domaine"] == "RH"
    assert result["nb_membres"] == 0
    assert "membres" not in result


# ──────────────────────────────────────────────────────────────────────────────
# Unitaires — protection 403
# ──────────────────────────────────────────────────────────────────────────────


def test_routes_admin_refusent_user_non_admin(client, user_factory, auth_header):
    user = user_factory("USER")
    headers = auth_header(user)
    assert client.get(f"{API}/admin/groupes", headers=headers).status_code == 403
    assert client.get(f"{API}/admin/gestionnaires", headers=headers).status_code == 403


def test_routes_admin_refusent_sans_token(client):
    assert client.get(f"{API}/admin/groupes").status_code == 401


# ──────────────────────────────────────────────────────────────────────────────
# Intégration — groupes CRUD
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.integration
def test_create_groupe(client, admin_headers):
    domaine = str(uuid.uuid4())[:8].upper()
    r = client.post(
        f"{API}/admin/groupes",
        json={"nom": "Support", "domaine": domaine},
        headers=admin_headers,
    )
    assert r.status_code == 201
    data = r.json()
    assert data["nom"] == "Support"
    assert data["domaine"] == domaine
    assert "id" in data


@pytest.mark.integration
def test_create_groupe_domaine_uppercase(client, admin_headers):
    domaine = str(uuid.uuid4())[:8].lower()
    r = client.post(
        f"{API}/admin/groupes",
        json={"nom": "Test", "domaine": domaine},
        headers=admin_headers,
    )
    assert r.status_code == 201
    assert r.json()["domaine"] == domaine.upper()


@pytest.mark.integration
def test_create_groupe_domaine_vide_rejete(client, admin_headers):
    r = client.post(
        f"{API}/admin/groupes",
        json={"nom": "X", "domaine": "   "},
        headers=admin_headers,
    )
    assert r.status_code == 422


@pytest.mark.integration
def test_create_groupe_domaine_duplique_409(client, admin_headers, groupe_factory):
    g = groupe_factory()
    r = client.post(
        f"{API}/admin/groupes",
        json={"nom": "Autre", "domaine": g.domaine},
        headers=admin_headers,
    )
    assert r.status_code == 409


@pytest.mark.integration
def test_list_groupes(client, admin_headers, groupe_factory):
    groupe_factory(nom="G1")
    groupe_factory(nom="G2")
    r = client.get(f"{API}/admin/groupes", headers=admin_headers)
    assert r.status_code == 200
    noms = [g["nom"] for g in r.json()]
    assert "G1" in noms
    assert "G2" in noms


@pytest.mark.integration
def test_delete_groupe(client, admin_headers, groupe_factory):
    g = groupe_factory()
    r = client.delete(f"{API}/admin/groupes/{g.id}", headers=admin_headers)
    assert r.status_code == 204
    # Le groupe ne doit plus apparaître dans la liste
    groupes = client.get(f"{API}/admin/groupes", headers=admin_headers).json()
    assert all(grp["id"] != str(g.id) for grp in groupes)


@pytest.mark.integration
def test_delete_groupe_inexistant_404(client, admin_headers):
    r = client.delete(f"{API}/admin/groupes/{uuid.uuid4()}", headers=admin_headers)
    assert r.status_code == 404


@pytest.mark.integration
def test_list_domaines(client, admin_headers, groupe_factory):
    dom = str(uuid.uuid4())[:6].upper()
    groupe_factory(domaine=dom)
    r = client.get(f"{API}/admin/domaines", headers=admin_headers)
    assert r.status_code == 200
    assert dom in r.json()


# ──────────────────────────────────────────────────────────────────────────────
# Intégration — membres
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.integration
def test_add_membre(client, admin_headers, groupe_factory, user_factory):
    g = groupe_factory()
    u = user_factory("USER")
    r = client.post(f"{API}/admin/groupes/{g.id}/membres/{u.id}", headers=admin_headers)
    assert r.status_code == 201
    membres = r.json()["membres"]
    assert any(m["id"] == str(u.id) for m in membres)


@pytest.mark.integration
def test_add_membre_idempotent(client, admin_headers, groupe_factory, user_factory):
    g = groupe_factory()
    u = user_factory("USER")
    client.post(f"{API}/admin/groupes/{g.id}/membres/{u.id}", headers=admin_headers)
    r = client.post(f"{API}/admin/groupes/{g.id}/membres/{u.id}", headers=admin_headers)
    assert r.status_code == 201
    assert len(r.json()["membres"]) == 1


@pytest.mark.integration
def test_add_membre_groupe_inexistant_404(client, admin_headers, user_factory):
    u = user_factory("USER")
    r = client.post(f"{API}/admin/groupes/{uuid.uuid4()}/membres/{u.id}", headers=admin_headers)
    assert r.status_code == 404


@pytest.mark.integration
def test_add_membre_user_inexistant_404(client, admin_headers, groupe_factory):
    g = groupe_factory()
    r = client.post(f"{API}/admin/groupes/{g.id}/membres/{uuid.uuid4()}", headers=admin_headers)
    assert r.status_code == 404


@pytest.mark.integration
def test_remove_membre(client, admin_headers, groupe_factory, user_factory):
    g = groupe_factory()
    u = user_factory("USER")
    client.post(f"{API}/admin/groupes/{g.id}/membres/{u.id}", headers=admin_headers)
    r = client.delete(f"{API}/admin/groupes/{g.id}/membres/{u.id}", headers=admin_headers)
    assert r.status_code == 204
    membres = client.get(f"{API}/admin/groupes", headers=admin_headers).json()
    grp = next(g2 for g2 in membres if g2["id"] == str(g.id))
    assert all(m["id"] != str(u.id) for m in grp["membres"])


@pytest.mark.integration
def test_remove_membre_groupe_inexistant_404(client, admin_headers, user_factory):
    u = user_factory("USER")
    r = client.delete(f"{API}/admin/groupes/{uuid.uuid4()}/membres/{u.id}", headers=admin_headers)
    assert r.status_code == 404


# ──────────────────────────────────────────────────────────────────────────────
# Intégration — chef
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.integration
def test_set_chef_true(client, admin_headers, groupe_factory, user_factory):
    g = groupe_factory()
    u = user_factory("USER")
    client.post(f"{API}/admin/groupes/{g.id}/membres/{u.id}", headers=admin_headers)
    r = client.put(
        f"{API}/admin/groupes/{g.id}/membres/{u.id}/chef",
        json={"is_chef": True},
        headers=admin_headers,
    )
    assert r.status_code == 200
    membres = r.json()["membres"]
    membre = next(m for m in membres if m["id"] == str(u.id))
    assert membre["is_chef"] is True


@pytest.mark.integration
def test_set_chef_false(client, admin_headers, groupe_factory, user_factory):
    g = groupe_factory()
    u = user_factory("USER")
    client.post(f"{API}/admin/groupes/{g.id}/membres/{u.id}", headers=admin_headers)
    client.put(
        f"{API}/admin/groupes/{g.id}/membres/{u.id}/chef",
        json={"is_chef": True},
        headers=admin_headers,
    )
    r = client.put(
        f"{API}/admin/groupes/{g.id}/membres/{u.id}/chef",
        json={"is_chef": False},
        headers=admin_headers,
    )
    assert r.status_code == 200
    membres = r.json()["membres"]
    membre = next(m for m in membres if m["id"] == str(u.id))
    assert membre["is_chef"] is False


@pytest.mark.integration
def test_set_chef_membre_inexistant_404(client, admin_headers, groupe_factory):
    g = groupe_factory()
    r = client.put(
        f"{API}/admin/groupes/{g.id}/membres/{uuid.uuid4()}/chef",
        json={"is_chef": True},
        headers=admin_headers,
    )
    assert r.status_code == 404


@pytest.mark.integration
def test_set_chef_groupe_inexistant_404(client, admin_headers, user_factory):
    u = user_factory("USER")
    r = client.put(
        f"{API}/admin/groupes/{uuid.uuid4()}/membres/{u.id}/chef",
        json={"is_chef": True},
        headers=admin_headers,
    )
    assert r.status_code == 404


# ──────────────────────────────────────────────────────────────────────────────
# Intégration — gestionnaires
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.integration
def test_list_gestionnaires(client, admin_factory, auth_header, db_session, monkeypatch):
    from app.config import settings
    from app.models.user import User

    # Force le fallback base (indépendant de AUTH_MODE=ldap dans l'environnement)
    monkeypatch.setattr(settings, "auth_mode", "db")

    admin = admin_factory()
    headers = auth_header(admin)

    g = User(
        email=f"{uuid.uuid4()}@test.local",
        role="USER",
        is_gestionnaire=True,
    )
    db_session.add(g)
    db_session.commit()

    r = client.get(f"{API}/admin/gestionnaires", headers=headers)
    assert r.status_code == 200
    ids = [u["id"] for u in r.json()]
    assert str(g.id) in ids


@pytest.mark.integration
def test_list_gestionnaires_exclut_non_gestionnaires(client, admin_factory, auth_header, db_session, monkeypatch):
    from app.config import settings
    from app.models.user import User

    # Force le fallback base (indépendant de AUTH_MODE=ldap dans l'environnement)
    monkeypatch.setattr(settings, "auth_mode", "db")

    admin = admin_factory()
    headers = auth_header(admin)

    non_g = User(
        email=f"{uuid.uuid4()}@test.local",
        role="USER",
        is_gestionnaire=False,
    )
    db_session.add(non_g)
    db_session.commit()

    r = client.get(f"{API}/admin/gestionnaires", headers=headers)
    assert r.status_code == 200
    ids = [u["id"] for u in r.json()]
    assert str(non_g.id) not in ids
