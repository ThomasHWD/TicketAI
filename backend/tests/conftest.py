"""Fixtures partagées par la suite de tests.

Deux catégories de tests coexistent (cf. plan) :

* **unitaires** — mockés, sans infrastructure : tournent partout, instantanément ;
* **intégration** (`@pytest.mark.integration`) — nécessitent une vraie base
  Postgres (et, pour ``test_search``, un vrai Qdrant). GitHub Actions provisionne
  ces services de façon déterministe et y exécute la suite complète. En local,
  si l'infra n'est pas joignable, ces tests sont **automatiquement ignorés**
  (skip) pour qu'un simple ``pytest`` reste vert sans ``make up``.
"""

from unittest.mock import MagicMock

# Import des modèles pour peupler Base.metadata (create_all/drop_all).
# NB : on utilise un alias pour ne PAS réintroduire le nom ``app`` dans ce module,
# sinon il masquerait l'instance FastAPI ``app`` importée ci-dessous (le fixture
# ``client`` recevrait alors le module et non l'application).
import app.models as _models  # noqa: F401  (effet de bord : enregistre les tables)
import pytest
from app.config import settings
from app.database import Base, SessionLocal, engine
from app.main import app
from fastapi.testclient import TestClient
from sqlalchemy import text

# Ordre FK-safe pour le nettoyage inter-tests : on supprime d'abord les tables
# qui référencent les autres.
_CLEANUP_ORDER = ("reponse_chunks", "reponses", "tickets", "users")


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
    skip_marker = pytest.mark.skip(
        reason="Infra indisponible (Postgres/Qdrant/Valkey) — test d'intégration ignoré"
    )
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip_marker)


@pytest.fixture(scope="session")
def db_schema():
    """Crée le schéma sur la base de test une fois pour toute la session."""
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db_session(db_schema):
    """Session SQLAlchemy avec nettoyage des tables après chaque test."""
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
def client(db_schema):
    """Client HTTP FastAPI (les routes ouvrent leur propre SessionLocal)."""
    with TestClient(app) as test_client:
        yield test_client


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
    """
    import app.api.v1.reponses as reponses_module

    feedback_mock = MagicMock()
    delete_point_mock = MagicMock()
    monkeypatch.setattr(reponses_module.feedback_job, "apply_async", feedback_mock)
    monkeypatch.setattr(reponses_module, "delete_response_point", delete_point_mock)
    return _SideEffectMocks(feedback_mock, delete_point_mock)
