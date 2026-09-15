"""Tests pour les endpoints /api/v1/admin/incidents et actions associées.

Unitaires (sans infra) :
  - Protection 401 / 403
  - _scan_document_incidents : parsing Redis mocké
  - retry_ticket sur ticket non-ÉCHOUÉ → 409
  - download_document : tâche Redis introuvable → 404
  - retry_document : tâche Redis introuvable → 404

Intégration (@pytest.mark.integration — nécessite Postgres réel) :
  - GET /incidents : structure de la réponse
  - GET /incidents : remonte les tickets ÉCHOUÉ
  - GET /incidents : remonte les tickets bloqués (EN_COURS > 10 min)
  - GET /incidents : n'inclut pas les tickets EN_COURS récents ni TERMINÉ
  - POST /tickets/{id}/retry : remet ÉCHOUÉ → EN_ATTENTE et dispatch le job
  - POST /tickets/{id}/retry : 409 si statut != ÉCHOUÉ ou EN_COURS
  - POST /tickets/{id}/retry : 404 si ticket inconnu
  - GET /documents/{task_id}/download : 404 si fichier absent sur disque
  - POST /documents/{task_id}/retry : 409 si fichier temporaire introuvable
"""

import json
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

API = "/api/v1"


# ──────────────────────────────────────────────────────────────────────────────
# Fixtures locales
# ──────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def admin_user(db_session):
    from app.models.user import User

    u = User(email=f"{uuid.uuid4()}@test.local", role="ADMIN")
    db_session.add(u)
    db_session.commit()
    db_session.refresh(u)
    return u


@pytest.fixture
def admin_headers(admin_user, auth_header):
    return auth_header(admin_user)


@pytest.fixture
def ticket_factory(db_session):
    from app.models.ticket import Ticket

    def _make(statut_job="EN_ATTENTE", domaine="RH", created_at=None):
        t = Ticket(
            question="Question de test",
            domaine=domaine,
            statut_job=statut_job,
            created_at=created_at or datetime.now(timezone.utc),
            job_id=uuid.uuid4(),
        )
        db_session.add(t)
        db_session.commit()
        db_session.refresh(t)
        return t

    return _make


# ──────────────────────────────────────────────────────────────────────────────
# Unitaires — protection
# ──────────────────────────────────────────────────────────────────────────────


def test_incidents_refus_sans_token(client):
    assert client.get(f"{API}/admin/incidents").status_code == 401


@pytest.mark.integration
def test_incidents_refus_non_admin(client, user_factory, auth_header):
    u = user_factory("USER")
    headers = auth_header(u)
    assert client.get(f"{API}/admin/incidents", headers=headers).status_code == 403


def test_retry_ticket_refus_sans_token(client):
    assert client.post(f"{API}/admin/tickets/{uuid.uuid4()}/retry").status_code == 401


def test_download_document_refus_sans_token(client):
    assert client.get(f"{API}/admin/documents/fake-task-id/download").status_code == 401


def test_retry_document_refus_sans_token(client):
    assert client.post(f"{API}/admin/documents/fake-task-id/retry").status_code == 401


# ──────────────────────────────────────────────────────────────────────────────
# Unitaires — _scan_document_incidents (Redis mocké)
# ──────────────────────────────────────────────────────────────────────────────


def test_scan_document_incidents_vide():
    """Aucune tâche Redis → liste vide."""
    from app.services.admin_service import scan_document_incidents as _scan_document_incidents

    with patch("app.services.admin_service.redis_lib") as mock_redis_lib:
        mock_r = MagicMock()
        mock_redis_lib.from_url.return_value = mock_r
        mock_r.scan_iter.return_value = []
        result = _scan_document_incidents()

    assert result == []


def test_scan_document_incidents_filtre_status_success():
    """Une tâche SUCCESS ne doit pas apparaître."""
    from app.services.admin_service import scan_document_incidents as _scan_document_incidents

    task_id = str(uuid.uuid4())
    meta = json.dumps(
        {
            "status": "SUCCESS",
            "task_name": "app.workers.ingestion.ingestion_job",
            "kwargs": {"filename": "doc.pdf", "domaine": "RH"},
        }
    ).encode()

    with patch("app.services.admin_service.redis_lib") as mock_redis_lib:
        mock_r = MagicMock()
        mock_redis_lib.from_url.return_value = mock_r
        mock_r.scan_iter.return_value = [f"celery-task-meta-{task_id}".encode()]
        mock_r.get.return_value = meta
        result = _scan_document_incidents()

    assert result == []


def test_scan_document_incidents_filtre_non_ingestion():
    """Une tâche FAILURE hors ingestion ne doit pas apparaître."""
    from app.services.admin_service import scan_document_incidents as _scan_document_incidents

    task_id = str(uuid.uuid4())
    meta = json.dumps(
        {
            "status": "FAILURE",
            "task_name": "app.workers.question.question_job",
            "kwargs": {},
        }
    ).encode()

    with patch("app.services.admin_service.redis_lib") as mock_redis_lib:
        mock_r = MagicMock()
        mock_redis_lib.from_url.return_value = mock_r
        mock_r.scan_iter.return_value = [f"celery-task-meta-{task_id}".encode()]
        mock_r.get.return_value = meta
        result = _scan_document_incidents()

    assert result == []


def test_scan_document_incidents_retourne_incident():
    """Une tâche FAILURE ingestion doit être retournée avec ses kwargs."""
    from app.services.admin_service import scan_document_incidents as _scan_document_incidents

    task_id = str(uuid.uuid4())
    meta = json.dumps(
        {
            "status": "FAILURE",
            "task_name": "app.workers.ingestion.ingestion_job",
            "kwargs": {"filename": "rapport.pdf", "domaine": "IT", "file_path": "/tmp/x.pdf"},
            "result": {"exc_message": ["Erreur de parsing"]},
        }
    ).encode()

    with patch("app.services.admin_service.redis_lib") as mock_redis_lib:
        mock_r = MagicMock()
        mock_redis_lib.from_url.return_value = mock_r
        mock_r.scan_iter.return_value = [f"celery-task-meta-{task_id}".encode()]
        mock_r.get.return_value = meta
        result = _scan_document_incidents()

    assert len(result) == 1
    assert result[0].task_id == task_id
    assert result[0].filename == "rapport.pdf"
    assert result[0].domaine == "IT"
    assert "Erreur de parsing" in (result[0].erreur or "")


# ──────────────────────────────────────────────────────────────────────────────
# Unitaires — download / retry document (Redis mocké)
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.integration
def test_download_document_tache_introuvable(client, user_factory, auth_header, db_session):
    admin = user_factory("ADMIN")
    headers = auth_header(admin)

    with patch("app.api.v1.admin.incidents.redis_lib") as mock_redis_lib:
        mock_r = MagicMock()
        mock_redis_lib.from_url.return_value = mock_r
        mock_r.get.return_value = None
        r = client.get(f"{API}/admin/documents/inexistant/download", headers=headers)

    assert r.status_code == 404


@pytest.mark.integration
def test_download_document_fichier_absent_disque(client, user_factory, auth_header, tmp_path):
    admin = user_factory("ADMIN")
    headers = auth_header(admin)

    task_id = str(uuid.uuid4())
    meta = json.dumps(
        {
            "status": "FAILURE",
            "kwargs": {"filename": "doc.pdf", "file_path": "/tmp/inexistant_xyz.pdf"},
        }
    ).encode()

    with patch("app.api.v1.admin.incidents.redis_lib") as mock_redis_lib:
        mock_r = MagicMock()
        mock_redis_lib.from_url.return_value = mock_r
        mock_r.get.return_value = meta
        r = client.get(f"{API}/admin/documents/{task_id}/download", headers=headers)

    assert r.status_code == 404


@pytest.mark.integration
def test_retry_document_tache_introuvable(client, user_factory, auth_header):
    admin = user_factory("ADMIN")
    headers = auth_header(admin)

    with patch("app.api.v1.admin.incidents.redis_lib") as mock_redis_lib:
        mock_r = MagicMock()
        mock_redis_lib.from_url.return_value = mock_r
        mock_r.get.return_value = None
        r = client.post(f"{API}/admin/documents/inexistant/retry", headers=headers)

    assert r.status_code == 404


@pytest.mark.integration
def test_retry_document_fichier_absent_409(client, user_factory, auth_header):
    admin = user_factory("ADMIN")
    headers = auth_header(admin)

    task_id = str(uuid.uuid4())
    meta = json.dumps(
        {
            "status": "FAILURE",
            "kwargs": {"filename": "doc.pdf", "file_path": "/tmp/inexistant_xyz_abc.pdf"},
        }
    ).encode()

    with patch("app.api.v1.admin.incidents.redis_lib") as mock_redis_lib:
        mock_r = MagicMock()
        mock_redis_lib.from_url.return_value = mock_r
        mock_r.get.return_value = meta
        r = client.post(f"{API}/admin/documents/{task_id}/retry", headers=headers)

    assert r.status_code == 409
    assert "re-uploader" in r.json()["detail"].lower()


# ──────────────────────────────────────────────────────────────────────────────
# Intégration — GET /incidents
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.integration
def test_incidents_structure_vide(client, admin_headers):
    with patch("app.api.v1.admin.incidents.scan_document_incidents", return_value=[]):
        r = client.get(f"{API}/admin/incidents", headers=admin_headers)

    assert r.status_code == 200
    data = r.json()
    assert "tickets_echoues" in data
    assert "tickets_bloques" in data
    assert "documents_echoues" in data
    assert isinstance(data["tickets_echoues"], list)
    assert isinstance(data["tickets_bloques"], list)
    assert isinstance(data["documents_echoues"], list)


@pytest.mark.integration
def test_incidents_remonte_tickets_echoues(client, admin_headers, ticket_factory):
    t = ticket_factory(statut_job="ÉCHOUÉ")

    with patch("app.api.v1.admin.incidents.scan_document_incidents", return_value=[]):
        r = client.get(f"{API}/admin/incidents", headers=admin_headers)

    assert r.status_code == 200
    ids = [t2["id"] for t2 in r.json()["tickets_echoues"]]
    assert str(t.id) in ids


@pytest.mark.integration
def test_incidents_remonte_tickets_bloques(client, admin_headers, ticket_factory):
    ancien = datetime.now(timezone.utc) - timedelta(minutes=15)
    t = ticket_factory(statut_job="EN_COURS", created_at=ancien)

    with patch("app.api.v1.admin.incidents.scan_document_incidents", return_value=[]):
        r = client.get(f"{API}/admin/incidents", headers=admin_headers)

    assert r.status_code == 200
    ids = [t2["id"] for t2 in r.json()["tickets_bloques"]]
    assert str(t.id) in ids


@pytest.mark.integration
def test_incidents_exclut_tickets_en_cours_recents(client, admin_headers, ticket_factory):
    t = ticket_factory(statut_job="EN_COURS")  # created_at = maintenant

    with patch("app.api.v1.admin.incidents.scan_document_incidents", return_value=[]):
        r = client.get(f"{API}/admin/incidents", headers=admin_headers)

    assert r.status_code == 200
    ids_bloques = [t2["id"] for t2 in r.json()["tickets_bloques"]]
    assert str(t.id) not in ids_bloques


@pytest.mark.integration
def test_incidents_exclut_tickets_termines(client, admin_headers, ticket_factory):
    t = ticket_factory(statut_job="TERMINÉ")

    with patch("app.api.v1.admin.incidents.scan_document_incidents", return_value=[]):
        r = client.get(f"{API}/admin/incidents", headers=admin_headers)

    assert r.status_code == 200
    tous = r.json()["tickets_echoues"] + r.json()["tickets_bloques"]
    ids = [t2["id"] for t2 in tous]
    assert str(t.id) not in ids


@pytest.mark.integration
def test_incidents_champs_ticket(client, admin_headers, ticket_factory):
    t = ticket_factory(statut_job="ÉCHOUÉ", domaine="IT")

    with patch("app.api.v1.admin.incidents.scan_document_incidents", return_value=[]):
        r = client.get(f"{API}/admin/incidents", headers=admin_headers)

    echoues = r.json()["tickets_echoues"]
    found = next((t2 for t2 in echoues if t2["id"] == str(t.id)), None)
    assert found is not None
    assert found["domaine"] == "IT"
    assert "question" in found
    assert "statut_job" in found
    assert "created_at" in found


# ──────────────────────────────────────────────────────────────────────────────
# Intégration — POST /tickets/{id}/retry
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.integration
def test_retry_ticket_echoue(client, admin_headers, ticket_factory, db_session):

    t = ticket_factory(statut_job="ÉCHOUÉ")

    with patch("app.workers.question.question_job.apply_async") as mock_dispatch:
        r = client.post(f"{API}/admin/tickets/{t.id}/retry", headers=admin_headers)

    assert r.status_code == 200
    assert "job_id" in r.json()

    db_session.refresh(t)
    assert t.statut_job == "EN_ATTENTE"
    assert t.erreur is None
    assert t.nb_retries == 1
    mock_dispatch.assert_called_once()


@pytest.mark.integration
def test_retry_ticket_bloque(client, admin_headers, ticket_factory, db_session):
    ancien = datetime.now(timezone.utc) - timedelta(minutes=15)
    t = ticket_factory(statut_job="EN_COURS", created_at=ancien)

    with patch("app.workers.question.question_job.apply_async"):
        r = client.post(f"{API}/admin/tickets/{t.id}/retry", headers=admin_headers)

    assert r.status_code == 200
    db_session.refresh(t)
    assert t.statut_job == "EN_ATTENTE"


@pytest.mark.integration
def test_retry_ticket_non_echoue_409(client, admin_headers, ticket_factory):
    t = ticket_factory(statut_job="TERMINÉ")
    r = client.post(f"{API}/admin/tickets/{t.id}/retry", headers=admin_headers)
    assert r.status_code == 409


@pytest.mark.integration
def test_retry_ticket_en_attente_409(client, admin_headers, ticket_factory):
    t = ticket_factory(statut_job="EN_ATTENTE")
    r = client.post(f"{API}/admin/tickets/{t.id}/retry", headers=admin_headers)
    assert r.status_code == 409


@pytest.mark.integration
def test_retry_ticket_inconnu_404(client, admin_headers):
    r = client.post(f"{API}/admin/tickets/{uuid.uuid4()}/retry", headers=admin_headers)
    assert r.status_code == 404


@pytest.mark.integration
def test_retry_ticket_incremente_nb_retries(client, admin_headers, ticket_factory, db_session):
    t = ticket_factory(statut_job="ÉCHOUÉ")

    with patch("app.workers.question.question_job.apply_async"):
        client.post(f"{API}/admin/tickets/{t.id}/retry", headers=admin_headers)
        db_session.refresh(t)
        assert t.nb_retries == 1

        t.statut_job = "ÉCHOUÉ"
        db_session.commit()

        client.post(f"{API}/admin/tickets/{t.id}/retry", headers=admin_headers)
        db_session.refresh(t)
        assert t.nb_retries == 2


@pytest.mark.integration
def test_retry_ticket_nouveau_job_id(client, admin_headers, ticket_factory, db_session):
    t = ticket_factory(statut_job="ÉCHOUÉ")
    ancien_job_id = t.job_id

    with patch("app.workers.question.question_job.apply_async"):
        r = client.post(f"{API}/admin/tickets/{t.id}/retry", headers=admin_headers)

    db_session.refresh(t)
    assert t.job_id != ancien_job_id
    assert str(t.job_id) == r.json()["job_id"]


# ──────────────────────────────────────────────────────────────────────────────
# Intégration — GET /documents/{task_id}/download (fichier présent)
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.integration
def test_download_document_fichier_present(client, admin_headers, tmp_path):
    fichier = tmp_path / "rapport.pdf"
    fichier.write_bytes(b"%PDF-1.4 fake content")

    task_id = str(uuid.uuid4())
    meta = json.dumps(
        {
            "status": "FAILURE",
            "kwargs": {"filename": "rapport.pdf", "file_path": str(fichier)},
        }
    ).encode()

    with patch("app.api.v1.admin.incidents.redis_lib") as mock_redis_lib:
        mock_r = MagicMock()
        mock_redis_lib.from_url.return_value = mock_r
        mock_r.get.return_value = meta
        r = client.get(f"{API}/admin/documents/{task_id}/download", headers=admin_headers)

    assert r.status_code == 200
    assert r.content == b"%PDF-1.4 fake content"


# ──────────────────────────────────────────────────────────────────────────────
# Intégration — POST /documents/{task_id}/retry (fichier présent)
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.integration
def test_delete_document_incident_supprime_redis(client, admin_headers):
    task_id = str(uuid.uuid4())
    meta = json.dumps(
        {
            "status": "FAILURE",
            "kwargs": {"filename": "doc.pdf", "file_path": "/tmp/inexistant.pdf"},
        }
    ).encode()

    with patch("app.api.v1.admin.incidents.redis_lib") as mock_redis_lib:
        mock_r = MagicMock()
        mock_redis_lib.from_url.return_value = mock_r
        mock_r.get.return_value = meta
        r = client.delete(f"{API}/admin/documents/{task_id}", headers=admin_headers)

    assert r.status_code == 204
    mock_r.delete.assert_called_once_with(f"celery-task-meta-{task_id}")


@pytest.mark.integration
def test_delete_document_incident_supprime_fichier(client, admin_headers, tmp_path):
    fichier = tmp_path / "doc.pdf"
    fichier.write_bytes(b"content")

    task_id = str(uuid.uuid4())
    meta = json.dumps(
        {
            "status": "FAILURE",
            "kwargs": {"filename": "doc.pdf", "file_path": str(fichier)},
        }
    ).encode()

    with patch("app.api.v1.admin.incidents.redis_lib") as mock_redis_lib:
        mock_r = MagicMock()
        mock_redis_lib.from_url.return_value = mock_r
        mock_r.get.return_value = meta
        client.delete(f"{API}/admin/documents/{task_id}", headers=admin_headers)

    assert not fichier.exists()


@pytest.mark.integration
def test_delete_document_incident_tache_introuvable(client, admin_headers):
    with patch("app.api.v1.admin.incidents.redis_lib") as mock_redis_lib:
        mock_r = MagicMock()
        mock_redis_lib.from_url.return_value = mock_r
        mock_r.get.return_value = None
        r = client.delete(f"{API}/admin/documents/inexistant", headers=admin_headers)

    assert r.status_code == 404


@pytest.mark.integration
def test_retry_document_fichier_present(client, admin_headers, tmp_path):
    fichier = tmp_path / "doc.pdf"
    fichier.write_bytes(b"content")

    task_id = str(uuid.uuid4())
    kwargs = {
        "filename": "doc.pdf",
        "file_path": str(fichier),
        "domaine": "RH",
        "description": "",
        "content_hash": "abc123",
    }
    meta = json.dumps({"status": "FAILURE", "kwargs": kwargs}).encode()

    with (
        patch("app.api.v1.admin.incidents.redis_lib") as mock_redis_lib,
        patch("app.workers.ingestion.ingestion_job.apply_async") as mock_dispatch,
    ):
        mock_r = MagicMock()
        mock_redis_lib.from_url.return_value = mock_r
        mock_r.get.return_value = meta
        r = client.post(f"{API}/admin/documents/{task_id}/retry", headers=admin_headers)

    assert r.status_code == 200
    assert "task_id" in r.json()
    mock_dispatch.assert_called_once()
    call_kwargs = mock_dispatch.call_args[1]["kwargs"]
    assert call_kwargs["filename"] == "doc.pdf"
    assert call_kwargs["domaine"] == "RH"
