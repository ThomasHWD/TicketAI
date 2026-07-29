"""Fixtures partagées par la suite de tests.

Deux catégories de tests coexistent (cf. plan) :

* **unitaires** — mockés, sans infrastructure : tournent partout, instantanément ;
* **intégration** (`@pytest.mark.integration`) — nécessitent une vraie base
  Postgres (et, pour ``test_search``, un vrai Qdrant). GitHub Actions provisionne
  ces services de façon déterministe et y exécute la suite complète. En local,
  si l'infra n'est pas joignable, ces tests sont **automatiquement ignorés**
  (skip) pour qu'un simple ``pytest`` reste vert sans ``make up``.
"""

import os
from pathlib import Path
from unittest.mock import MagicMock

# ── Isolation de la base de test (CRITIQUE) ────────────────────────────
# On force, AVANT tout import applicatif, une base dédiée dont le nom se termine
# par « _test ». `engine` et `SessionLocal` (dans app.database) sont construits à
# l'import à partir de `settings.postgres_db` : en surchargeant la variable
# d'environnement ici, TOUTE la couche d'accès (routes, workers, fixtures) est
# reliée à la base de test. Conséquence : un simple ``pytest`` ne peut JAMAIS
# vider la base de dev (ex. ticketai_db) — le nettoyage inter-tests s'exécute
# exclusivement sur `<db>_test`.


def _force_test_db() -> None:
    base = os.environ.get("POSTGRES_DB")
    if not base:  # non défini dans l'environnement → on lit le .env du backend
        env_file = Path(__file__).resolve().parents[1] / ".env"
        if env_file.exists():
            for line in env_file.read_text().splitlines():
                if line.strip().startswith("POSTGRES_DB="):
                    base = line.split("=", 1)[1].strip().strip("\"'")
                    break
    base = base or "ticketai"
    os.environ["POSTGRES_DB"] = base if base.endswith("_test") else f"{base}_test"


_force_test_db()

# Import des modèles pour peupler Base.metadata (create_all/drop_all).
# NB : on utilise un alias pour ne PAS réintroduire le nom ``app`` dans ce module,
# sinon il masquerait l'instance FastAPI ``app`` importée ci-dessous (le fixture
# ``client`` recevrait alors le module et non l'application).
import app.models as _models  # noqa: E402,F401  (effet de bord : enregistre les tables)
import pytest  # noqa: E402
from app.config import settings  # noqa: E402
from app.database import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402


def _ensure_test_database() -> None:
    """Crée la base de test si elle n'existe pas (connexion à la base ``postgres``)."""
    admin_url = (
        f"postgresql://{settings.postgres_user}:{settings.postgres_password}"
        f"@{settings.postgres_host}:{settings.postgres_port}/postgres"
    )
    try:
        admin_engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
        with admin_engine.connect() as conn:
            exists = conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :n"),
                {"n": settings.postgres_db},
            ).scalar()
            if not exists:
                conn.execute(text(f'CREATE DATABASE "{settings.postgres_db}"'))
        admin_engine.dispose()
    except Exception:
        pass  # serveur injoignable → _db_available() renverra False (tests skippés)


# Ordre FK-safe pour le nettoyage inter-tests : on supprime d'abord les tables
# qui référencent les autres.
_CLEANUP_ORDER = ("reponse_chunks", "reponses", "tickets", "user_groups", "groupes", "users", "site_config")


def _db_available() -> bool:
    """Teste une seule fois si la base est joignable au démarrage de la session.

    **Garde-fou destructif :** les fixtures créent/suppriment le schéma et vident
    les tables entre chaque test. On refuse donc de tourner tant que la base
    ciblée n'est pas manifestement une base de test (son nom doit contenir
    ``test``). Cela évite d'effacer une base de dev locale (`ticketai_db`). En CI
    la base est `ticketai_test` → OK.
    """
    if "test" not in settings.postgres_db.lower():
        return False
    _ensure_test_database()
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


DB_AVAILABLE = _db_available()


def pytest_collection_modifyitems(config, items):
    """Skip automatique des tests `integration` quand l'infra est absente.

    Sur GitHub Actions (Postgres/Valkey/Qdrant en services) `DB_AVAILABLE` est
    vrai → rien n'est ignoré, la suite complète tourne. En local sans `make up`,
    les tests d'intégration sont marqués skip *avant* toute exécution de fixture.
    """
    if DB_AVAILABLE:
        return
    skip_marker = pytest.mark.skip(reason="Infra indisponible (Postgres/Qdrant/Valkey) — test d'intégration ignoré")
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip_marker)


@pytest.fixture(scope="session")
def db_schema():
    """Crée le schéma sur la base de test une fois pour toute la session.

    No-op si DB_AVAILABLE est faux — ce garde-fou empêche tout drop_all
    accidentel sur une base de dev (le nom doit contenir "test").
    """
    if not DB_AVAILABLE:
        yield
        return
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db_session(db_schema):
    """Session SQLAlchemy avec nettoyage des tables après chaque test."""
    # Garde-fou : on ne vide JAMAIS une base dont le nom ne contient pas "test".
    assert "test" in settings.postgres_db.lower(), f"Refus de nettoyer une base hors-test : {settings.postgres_db}"
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        for table in _CLEANUP_ORDER:
            session.execute(text(f"DELETE FROM {table}"))
        session.commit()
        session.close()


@pytest.fixture
def client():
    """Client HTTP FastAPI pour les tests unitaires (sans schéma requis).

    Les tests d'intégration qui ont besoin du schéma doivent aussi demander
    db_session ou db_schema explicitement — ce qui active create_all/drop_all
    uniquement sur une base dont le nom contient "test".
    """
    with TestClient(app) as test_client:
        yield test_client


# ── Authentification (JWT réel signé pour les tests d'intégration) ──────


@pytest.fixture
def user_factory(db_session):
    """Crée un utilisateur en base et le renvoie (FK cible des routes protégées)."""
    import uuid

    from app.models.user import User

    def _make(role: str = "USER"):
        user = User(email=f"{uuid.uuid4()}@test.local", role=role)
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)
        return user

    return _make


@pytest.fixture
def auth_header():
    """Fabrique un header ``Authorization: Bearer <jwt>`` pour un User donné."""
    from app.core.security import create_access_token

    def _make(user) -> dict:
        return {"Authorization": f"Bearer {create_access_token(user.id, user.role)}"}

    return _make


@pytest.fixture
def auth_headers(user_factory, auth_header):
    """Header pour un utilisateur générique authentifié (rôle USER)."""
    return auth_header(user_factory("USER"))


class _SideEffectMocks:
    """Poignées vers les effets de bord mockés, pour les assertions."""

    def __init__(self, feedback: MagicMock, delete_point: MagicMock):
        self.feedback = feedback
        self.delete_point = delete_point


@pytest.fixture(autouse=True)
def mock_side_effects(monkeypatch):
    """Neutralise les effets de bord hors périmètre des tests d'API.

    ``feedback_job.apply_async`` (enqueue Celery/Valkey) et
    ``delete_response_point`` (appel Qdrant) sont remplacés par des mocks, de
    sorte que les tests d'intégration n'exercent que la logique métier + la base.
    ``init_collection`` est TOUJOURS mocké : c'est un effet de bord de démarrage
    (création de la collection Qdrant au lifespan FastAPI) hors périmètre des
    tests. Les tests de recherche qui ont besoin d'un vrai Qdrant montent leur
    propre collection via leur fixture dédiée (``setup_test_qdrant``).
    """
    import app.api.v1.reponses as reponses_module
    import app.main as main_module

    feedback_mock = MagicMock()
    delete_point_mock = MagicMock()
    monkeypatch.setattr(reponses_module.feedback_job, "apply_async", feedback_mock)
    monkeypatch.setattr(reponses_module, "delete_response_point", delete_point_mock)
    monkeypatch.setattr(main_module, "init_collection", MagicMock())
    return _SideEffectMocks(feedback_mock, delete_point_mock)
