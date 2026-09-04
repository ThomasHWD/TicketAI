"""Fixtures partagées pour les tests de documents."""

import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from .helpers import _TEXTE_V1, _doc_en_base


@pytest.fixture(autouse=True)
def _auth_override():
    """Neutralise l'authentification et la DB pour ces tests.

    - ``get_current_user`` → ADMIN factice (sans base)
    - ``get_db`` (module documents) → session mock avec domaines {"IT", "RH", "LEGAL"}
      préconfigurés pour que la validation de domaine passe sans Postgres réel.
    """
    from app.api.v1.documents.core import get_db
    from app.core.security import get_current_user
    from app.main import app
    from app.models.groupe import Groupe
    from app.models.user import User

    fake_admin = User(id=uuid.uuid4(), email="tester@test.local", role="ADMIN")
    fake_admin.groupes = [Groupe(domaine="IT"), Groupe(domaine="RH"), Groupe(domaine="LEGAL")]
    app.dependency_overrides[get_current_user] = lambda: fake_admin

    mock_db = MagicMock()
    mock_db.query.return_value.distinct.return_value.all.return_value = [("IT",), ("RH",), ("LEGAL",)]
    mock_db.query.return_value.filter.return_value.first.return_value = None
    app.dependency_overrides[get_db] = lambda: mock_db

    yield

    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def mock_qdrant(monkeypatch):
    """Remplace le client Qdrant dans app.api.v1.documents.core par un MagicMock."""
    import app.api.v1.documents.core as docs_module

    mock_client = MagicMock()
    mock_client.scroll.return_value = ([], None)
    monkeypatch.setattr(docs_module, "client", mock_client)
    return mock_client


@pytest.fixture
def db_reelle(db_session):
    """Branche les routes sur la vraie base de test, avec un admin réel en base."""
    from app.api.v1.documents.core import get_db
    from app.core.security import get_current_user
    from app.main import app
    from app.models.groupe import Groupe
    from app.models.user import User

    groupes = [Groupe(nom=f"Groupe {dom}", domaine=dom) for dom in ("IT", "RH", "LEGAL")]
    db_session.add_all(groupes)
    admin = User(email=f"{uuid.uuid4()}@test.local", role="ADMIN")
    admin.groupes = groupes
    db_session.add(admin)
    db_session.commit()

    app.dependency_overrides[get_current_user] = lambda: admin
    app.dependency_overrides[get_db] = lambda: db_session
    yield db_session
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def backoffice_it(db_reelle):
    """Validateur non-admin, membre du seul domaine IT."""
    from app.core.security import get_current_user
    from app.main import app
    from app.models.groupe import Groupe
    from app.models.user import User

    groupe_it = db_reelle.query(Groupe).filter(Groupe.domaine == "IT").first()
    user = User(email=f"{uuid.uuid4()}@test.local", role="VALIDATEUR")
    user.groupes = [groupe_it]
    db_reelle.add(user)
    db_reelle.commit()

    app.dependency_overrides[get_current_user] = lambda: user
    return user


@pytest.fixture
def admin_sans_groupe(db_reelle):
    """Administrateur membre d'aucun domaine."""
    from app.core.security import get_current_user
    from app.main import app
    from app.models.user import User

    user = User(email=f"{uuid.uuid4()}@test.local", role="ADMIN")
    db_reelle.add(user)
    db_reelle.commit()

    app.dependency_overrides[get_current_user] = lambda: user
    return user


@pytest.fixture
def mock_ingestion_job(monkeypatch):
    """Neutralise l'enqueue Celery pour les tests d'upload."""
    import app.api.v1.documents.core as docs_module

    mock_job = MagicMock()
    mock_task = MagicMock()
    mock_task.id = str(uuid.uuid4())
    mock_job.apply_async.return_value = mock_task
    monkeypatch.setattr(docs_module, "ingestion_job", mock_job)
    return mock_job


@pytest.fixture
def qdrant_maj(monkeypatch):
    """Patche le client Qdrant dans services/qdrant (capturer_chunks) et workers/document_update."""
    import app.services.qdrant as qdrant_module
    import app.workers.document_update as maj_module

    mock = MagicMock()
    mock.scroll.return_value = (
        [
            SimpleNamespace(payload={"chunk_index": i, "contenu": t.decode()})
            for i, t in enumerate(_TEXTE_V1.split(b"\n\n"))
        ],
        None,
    )
    monkeypatch.setattr(qdrant_module, "client", mock)
    monkeypatch.setattr(maj_module, "client", mock)
    return mock


@pytest.fixture
def mock_maj_job(monkeypatch):
    import app.api.v1.documents.versions as docs_module

    mock_job = MagicMock()
    mock_task = MagicMock()
    mock_task.id = str(uuid.uuid4())
    mock_job.apply_async.return_value = mock_task
    monkeypatch.setattr(docs_module, "document_update_job", mock_job)
    return mock_job


@pytest.fixture
def staging_tmp(tmp_path, monkeypatch):
    import app.services.document_service as docs_module

    monkeypatch.setattr(docs_module, "STAGING_DIR", str(tmp_path / "staging"))
    return tmp_path


@pytest.fixture
def qdrant_doc(db_reelle):
    """Document réel des deux côtés : ligne Postgres + points Qdrant."""
    from app.services.qdrant import COLLECTION_NAME
    from app.services.qdrant import client as real_client
    from qdrant_client import models as qdrant_models
    from qdrant_client.models import PointStruct, SparseVector

    if not real_client.collection_exists(COLLECTION_NAME):
        real_client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config={"dense": qdrant_models.VectorParams(size=1024, distance=qdrant_models.Distance.COSINE)},
            sparse_vectors_config={"sparse": qdrant_models.SparseVectorParams()},
        )

    doc_id = _doc_en_base(db_reelle, filename="integration_test.md", domaine="IT").doc_id
    points = [
        PointStruct(
            id=str(uuid.uuid4()),
            vector={
                "dense": [0.1] * 1024,
                "sparse": SparseVector(indices=[0, 1], values=[0.5, 0.5]),
            },
            payload={
                "doc_id": doc_id,
                "chunk_index": i,
                "source": "integration_test.md",
                "domaine": "IT",
                "contenu": f"Contenu intégration chunk {i}",
                "stored_path": None,
                "description": "Test d'intégration",
            },
        )
        for i in range(3)
    ]
    real_client.upsert(collection_name=COLLECTION_NAME, points=points)

    yield doc_id

    from qdrant_client.models import FieldCondition, Filter, FilterSelector, MatchValue

    real_client.delete(
        collection_name=COLLECTION_NAME,
        points_selector=FilterSelector(
            filter=Filter(must=[FieldCondition(key="doc_id", match=MatchValue(value=doc_id))])
        ),
    )


@pytest.fixture
def job_maj_reel(monkeypatch, tmp_path, qdrant_maj):
    """Le vrai `document_update_job`, branché sur la base réelle.

    Qdrant, l'embedding et le chunking sont mockés ; Postgres, le disque et la
    détection d'obsolescence sont réels. `qdrant_maj` fournit déjà le mock du
    module — le job et l'aperçu partagent ainsi la même vue de la version
    sortante, comme en production.
    """
    import app.api.v1.documents.versions as docs_module
    import app.workers.document_update as maj_module
    from app.config import settings

    monkeypatch.setattr(settings, "documents_storage_path", str(tmp_path / "storage"))
    monkeypatch.setattr(maj_module, "chunk_text", lambda pages: "\n\n".join(pages).split("\n\n"))
    monkeypatch.setattr(
        maj_module,
        "embed_texts",
        lambda chunks, is_query=False: [
            {"dense": [0.1] * 1024, "sparse": {"indices": [1], "values": [0.5]}} for _ in chunks
        ],
    )
    monkeypatch.setattr(maj_module, "broadcast_sync", MagicMock())

    import app.workers.reverification as reverif_module

    enfilees: list[dict] = []
    monkeypatch.setattr(reverif_module.reverification_job, "apply_async", lambda **kw: enfilees.append(kw))

    lance = MagicMock()
    lance.apply_async.return_value = SimpleNamespace(id=str(uuid.uuid4()))
    monkeypatch.setattr(docs_module, "document_update_job", lance)

    def executer():
        """Rejoue le job avec **exactement** les kwargs produits par `confirm`."""
        kwargs = lance.apply_async.call_args.kwargs["kwargs"]
        maj_module.document_update_job(**kwargs)
        return kwargs

    return SimpleNamespace(executer=executer, mock=lance, enfilees=enfilees)
