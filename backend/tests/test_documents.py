"""Tests pour les endpoints /api/v1/documents et les helpers d'ingestion.

Unitaires (pas d'infra) :
  - Validation de fichier (domaine, extension, taille, magic bytes, UTF-8)
  - sanitize_filename
  - extract_text sur .md
  - Listing, chunks, suppression via Qdrant mocké

Intégration (@pytest.mark.integration — nécessite Qdrant réel) :
  - Flux complet listing / chunks / delete sur une collection réelle
"""

import io
import os
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

API = "/api/v1"

# ──────────────────────────────────────────────────────────────────────────────
# Helpers partagés
# ──────────────────────────────────────────────────────────────────────────────

# Contenu minimal valide pour chaque format
_PDF_MAGIC = b"%PDF-1.4 fake content"
_DOCX_MAGIC = b"PK\x03\x04" + b"\x00" * 100  # archive ZIP minimale
_MD_CONTENT = b"# Titre\n\nContenu de test."


def _upload(client, *, domaine="IT", filename="doc.md", content=_MD_CONTENT, content_type="text/plain", description=""):
    """Helper qui poste un fichier vers POST /documents."""
    params = f"domaine={domaine}"
    if description:
        params += f"&description={description}"
    return client.post(
        f"{API}/documents?{params}",
        files={"file": (filename, io.BytesIO(content), content_type)},
    )


# ──────────────────────────────────────────────────────────────────────────────
# Fixture : mock du client Qdrant dans le module documents
# ──────────────────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _auth_override():
    """Neutralise l'authentification et la DB pour ces tests.

    - ``get_current_user`` → ADMIN factice (sans base)
    - ``get_db`` (module documents) → session mock avec domaines {"IT", "RH", "LEGAL"}
      préconfigurés pour que la validation de domaine passe sans Postgres réel.
    """
    from unittest.mock import MagicMock

    from app.api.v1.documents import get_db
    from app.core.security import get_current_user
    from app.main import app
    from app.models.user import User

    fake_admin = User(id=uuid.uuid4(), email="tester@test.local", role="ADMIN")
    app.dependency_overrides[get_current_user] = lambda: fake_admin

    # Session DB fictive : query(Groupe.domaine).distinct().all() → [("IT",), ("RH",), ("LEGAL",)]
    mock_db = MagicMock()
    mock_db.query.return_value.distinct.return_value.all.return_value = [("IT",), ("RH",), ("LEGAL",)]
    app.dependency_overrides[get_db] = lambda: mock_db

    yield

    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def mock_qdrant(monkeypatch):
    """Remplace le client Qdrant dans app.api.v1.documents par un MagicMock."""
    import app.api.v1.documents as docs_module

    mock_client = MagicMock()
    # scroll() renvoie ([], None) par défaut — les tests surchargent au besoin
    mock_client.scroll.return_value = ([], None)
    monkeypatch.setattr(docs_module, "client", mock_client)
    return mock_client


@pytest.fixture
def mock_ingestion_job(monkeypatch):
    """Neutralise l'enqueue Celery pour les tests d'upload."""
    import app.api.v1.documents as docs_module

    mock_job = MagicMock()
    mock_task = MagicMock()
    mock_task.id = str(uuid.uuid4())
    mock_job.apply_async.return_value = mock_task
    monkeypatch.setattr(docs_module, "ingestion_job", mock_job)
    return mock_job


# ──────────────────────────────────────────────────────────────────────────────
# Helpers ingestion : extract_text, clean_text, sanitize_filename
# ──────────────────────────────────────────────────────────────────────────────


class TestSanitizeFilename:
    def test_normal(self):
        from app.api.v1.documents import sanitize_filename

        assert sanitize_filename("rapport_2025.pdf") == "rapport_2025.pdf"

    def test_path_traversal(self):
        from app.api.v1.documents import sanitize_filename

        assert sanitize_filename("../../etc/passwd") == "passwd"

    def test_null_bytes(self):
        from app.api.v1.documents import sanitize_filename

        assert "\x00" not in sanitize_filename("fichier\x00.pdf")

    def test_special_chars_replaced(self):
        from app.api.v1.documents import sanitize_filename

        # Pas de "/" dans le nom pour éviter que basename le tronque
        result = sanitize_filename("doc (1); injection$.pdf")
        assert ";" not in result
        assert "$" not in result

    def test_empty_raises(self):
        from app.api.v1.documents import sanitize_filename
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc:
            sanitize_filename("")
        assert exc.value.status_code == 400

    def test_dot_only_raises(self):
        from app.api.v1.documents import sanitize_filename
        from fastapi import HTTPException

        with pytest.raises(HTTPException):
            sanitize_filename(".hidden")


class TestExtractText:
    def test_md_file(self, tmp_path):
        from app.workers.ingestion import extract_text

        f = tmp_path / "test.md"
        f.write_text("# Titre\n\nContenu de test.", encoding="utf-8")
        pages = extract_text(str(f))
        assert len(pages) == 1
        assert "Titre" in pages[0]

    def test_txt_file(self, tmp_path):
        from app.workers.ingestion import extract_text

        f = tmp_path / "test.txt"
        f.write_text("Texte simple.", encoding="utf-8")
        pages = extract_text(str(f))
        assert pages[0] == "Texte simple."

    def test_missing_file_raises(self, tmp_path):
        from app.workers.ingestion import extract_text

        with pytest.raises(FileNotFoundError):
            extract_text(str(tmp_path / "inexistant.md"))

    def test_unsupported_extension_raises(self, tmp_path):
        from app.workers.ingestion import extract_text

        f = tmp_path / "archive.zip"
        f.write_bytes(b"PK\x03\x04")
        with pytest.raises(ValueError):
            extract_text(str(f))

    def test_real_md_file(self):
        from app.workers.ingestion import extract_text

        fixture = Path(__file__).parent / "Accord_Teletravail_Reglementation.md"
        pages = extract_text(str(fixture))
        assert len(pages) >= 1
        assert len(pages[0]) > 20


class TestStoreFile:
    def test_moves_file_to_dest(self, tmp_path, monkeypatch):
        from app.workers.ingestion import store_file

        src = tmp_path / "source.md"
        src.write_text("contenu")
        dest_root = tmp_path / "storage"
        monkeypatch.setattr("app.workers.ingestion.settings", MagicMock(documents_storage_path=str(dest_root)))

        doc_id = str(uuid.uuid4())
        dest = store_file(str(src), doc_id, "source.md")

        assert os.path.exists(dest)
        assert not src.exists()  # déplacé, plus en place


# ──────────────────────────────────────────────────────────────────────────────
# POST /documents — validation
# ──────────────────────────────────────────────────────────────────────────────


class TestUploadValidation:
    def test_domaine_invalide(self, client, mock_ingestion_job):
        r = _upload(client, domaine="INCONNU")
        assert r.status_code == 400
        assert "Domaine invalide" in r.json()["detail"]

    def test_extension_non_supportee(self, client, mock_ingestion_job):
        r = _upload(client, filename="doc.xlsx", content=b"fake")
        assert r.status_code == 400
        assert "Extension non support" in r.json()["detail"]

    def test_pdf_magic_bytes_incorrect(self, client, mock_ingestion_job):
        r = _upload(client, filename="faux.pdf", content=b"NOTPDF content here")
        assert r.status_code == 400
        assert "incoh" in r.json()["detail"]

    def test_docx_magic_bytes_incorrect(self, client, mock_ingestion_job):
        r = _upload(client, filename="faux.docx", content=b"not a zip file!")
        assert r.status_code == 400

    def test_txt_non_utf8(self, client, mock_ingestion_job):
        r = _upload(client, filename="latin.txt", content=b"\xff\xfe binary garbage")
        assert r.status_code == 400
        assert "UTF-8" in r.json()["detail"]

    def test_fichier_trop_volumineux(self, client, mock_ingestion_job):
        big = b"x" * (51 * 1024 * 1024)  # 51 Mo
        r = _upload(client, content=big)
        assert r.status_code == 400
        assert "volumineux" in r.json()["detail"]

    def test_upload_md_valide(self, client, mock_ingestion_job):
        r = _upload(client, description="Document de test")
        assert r.status_code == 200
        body = r.json()
        assert body["statut"] == "EN_ATTENTE"
        assert body["filename"] == "doc.md"
        assert "job_id" in body

    def test_upload_pdf_valide(self, client, mock_ingestion_job):
        r = _upload(client, filename="rapport.pdf", content=_PDF_MAGIC)
        assert r.status_code == 200

    def test_description_transmise_au_job(self, client, mock_ingestion_job):
        _upload(client, description="Charte informatique 2025")
        # apply_async est appelé avec args=[file_path, filename, domaine, description]
        args_list = mock_ingestion_job.apply_async.call_args.kwargs["args"]
        assert args_list[3] == "Charte informatique 2025"

    def test_description_vide_par_defaut(self, client, mock_ingestion_job):
        _upload(client)
        args_list = mock_ingestion_job.apply_async.call_args.kwargs["args"]
        assert args_list[3] == ""

    def test_hash_transmis_au_job(self, client, mock_ingestion_job):
        _upload(client)
        args_list = mock_ingestion_job.apply_async.call_args.kwargs["args"]
        # args[4] = content_hash : doit être un SHA-256 hexadécimal (64 chars)
        assert len(args_list[4]) == 64
        assert all(c in "0123456789abcdef" for c in args_list[4])


class TestDuplicateDetection:
    def test_doublon_renvoie_deja_indexe(self, client, mock_qdrant, mock_ingestion_job):
        doc_id = str(uuid.uuid4())
        point = MagicMock()
        point.payload = {"doc_id": doc_id, "source": "doc.md", "content_hash": "abc"}
        # Premier scroll (vérification doublon) → trouvé
        mock_qdrant.scroll.return_value = ([point], None)

        r = _upload(client)
        assert r.status_code == 200
        body = r.json()
        assert body["statut"] == "DÉJÀ_INDEXÉ"
        assert body["doc_id"] == doc_id
        assert body["job_id"] is None
        # Aucun job Celery ne doit être lancé
        mock_ingestion_job.apply_async.assert_not_called()

    def test_doublon_meme_contenu_hash_identique(self, client, mock_qdrant, mock_ingestion_job):
        """Deux uploads du même contenu produisent le même hash."""
        import hashlib

        contenu = _MD_CONTENT
        hash1 = hashlib.sha256(contenu).hexdigest()

        mock_qdrant.scroll.return_value = ([], None)
        _upload(client, content=contenu)
        args1 = mock_ingestion_job.apply_async.call_args.kwargs["args"][4]
        assert args1 == hash1

    def test_contenu_different_n_est_pas_doublon(self, client, mock_qdrant, mock_ingestion_job):
        # Aucun point trouvé → ingestion normale
        mock_qdrant.scroll.return_value = ([], None)
        r = _upload(client, content=b"# Contenu unique A")
        assert r.status_code == 200
        assert r.json()["statut"] == "EN_ATTENTE"
        mock_ingestion_job.apply_async.assert_called_once()


# ──────────────────────────────────────────────────────────────────────────────
# GET /documents — listing (Qdrant mocké)
# ──────────────────────────────────────────────────────────────────────────────


def _make_point(doc_id, filename, domaine, chunk_index=0, description=""):
    p = MagicMock()
    p.payload = {
        "doc_id": doc_id,
        "source": filename,
        "domaine": domaine,
        "stored_path": f"/storage/{doc_id}/{filename}",
        "description": description,
        "chunk_index": chunk_index,
        "contenu": f"Contenu chunk {chunk_index}",
    }
    p.id = str(uuid.uuid4())
    return p


class TestListDocuments:
    def test_liste_vide(self, client, mock_qdrant):
        mock_qdrant.scroll.return_value = ([], None)
        r = client.get(f"{API}/documents")
        assert r.status_code == 200
        assert r.json() == {"total": 0, "items": []}

    def test_groupement_par_doc_id(self, client, mock_qdrant):
        doc_id = str(uuid.uuid4())
        points = [_make_point(doc_id, "charte.md", "IT", i) for i in range(3)]
        mock_qdrant.scroll.side_effect = [(points, None)]

        r = client.get(f"{API}/documents")
        body = r.json()
        assert body["total"] == 1
        assert body["items"][0]["nb_chunks"] == 3
        assert body["items"][0]["doc_id"] == doc_id
        assert body["items"][0]["filename"] == "charte.md"

    def test_plusieurs_docs(self, client, mock_qdrant):
        id1, id2 = str(uuid.uuid4()), str(uuid.uuid4())
        points = [
            _make_point(id1, "doc1.md", "IT"),
            _make_point(id1, "doc1.md", "IT", chunk_index=1),
            _make_point(id2, "doc2.md", "RH"),
        ]
        mock_qdrant.scroll.side_effect = [(points, None)]

        r = client.get(f"{API}/documents")
        body = r.json()
        assert body["total"] == 2
        chunks_by_id = {item["doc_id"]: item["nb_chunks"] for item in body["items"]}
        assert chunks_by_id[id1] == 2
        assert chunks_by_id[id2] == 1

    def test_description_presente(self, client, mock_qdrant):
        doc_id = str(uuid.uuid4())
        points = [_make_point(doc_id, "note.md", "RH", description="Note RH 2025")]
        mock_qdrant.scroll.side_effect = [(points, None)]

        r = client.get(f"{API}/documents")
        assert r.json()["items"][0]["description"] == "Note RH 2025"

    def test_filtre_domaine_inconnu_retourne_liste_vide(self, client, mock_qdrant):
        mock_qdrant.scroll.return_value = ([], None)
        r = client.get(f"{API}/documents?domaine=INCONNU")
        assert r.status_code == 200
        assert r.json()["items"] == []

    def test_filtre_domaine_valide_passe_au_scroll(self, client, mock_qdrant):
        mock_qdrant.scroll.return_value = ([], None)
        client.get(f"{API}/documents?domaine=RH")
        # scroll doit avoir été appelé avec un filtre (scroll_filter non None)
        call_kwargs = mock_qdrant.scroll.call_args.kwargs
        assert call_kwargs.get("scroll_filter") is not None

    def test_pagination_qdrant(self, client, mock_qdrant):
        """Vérifie que le scroll continue tant que l'offset n'est pas None."""
        id1, id2 = str(uuid.uuid4()), str(uuid.uuid4())
        page1 = [_make_point(id1, "a.md", "IT")]
        page2 = [_make_point(id2, "b.md", "IT")]
        # Première page renvoie un offset "next", deuxième renvoie None
        mock_qdrant.scroll.side_effect = [(page1, "offset_token"), (page2, None)]

        r = client.get(f"{API}/documents")
        assert r.json()["total"] == 2
        assert mock_qdrant.scroll.call_count == 2


# ──────────────────────────────────────────────────────────────────────────────
# GET /documents/{doc_id}/chunks
# ──────────────────────────────────────────────────────────────────────────────


class TestGetChunks:
    def test_chunks_tries_par_index(self, client, mock_qdrant):
        doc_id = str(uuid.uuid4())
        # Les points arrivent dans le désordre
        points = [_make_point(doc_id, "x.md", "IT", i) for i in [2, 0, 1]]
        mock_qdrant.scroll.return_value = (points, None)

        r = client.get(f"{API}/documents/{doc_id}/chunks")
        assert r.status_code == 200
        body = r.json()
        indices = [c["chunk_index"] for c in body["chunks"]]
        assert indices == sorted(indices)
        assert len(body["chunks"]) == 3

    def test_doc_inexistant_renvoie_404(self, client, mock_qdrant):
        mock_qdrant.scroll.return_value = ([], None)
        r = client.get(f"{API}/documents/{uuid.uuid4()}/chunks")
        assert r.status_code == 404

    def test_contenu_present(self, client, mock_qdrant):
        doc_id = str(uuid.uuid4())
        points = [_make_point(doc_id, "y.md", "IT", 0)]
        mock_qdrant.scroll.return_value = (points, None)

        r = client.get(f"{API}/documents/{doc_id}/chunks")
        assert "contenu" in r.json()["chunks"][0]


# ──────────────────────────────────────────────────────────────────────────────
# DELETE /documents/{doc_id}
# ──────────────────────────────────────────────────────────────────────────────


class TestDeleteDocument:
    def test_delete_doc_inexistant_renvoie_404(self, client, mock_qdrant):
        mock_qdrant.scroll.return_value = ([], None)
        r = client.delete(f"{API}/documents/{uuid.uuid4()}")
        assert r.status_code == 404

    def test_delete_appelle_qdrant_delete(self, client, mock_qdrant, tmp_path):
        doc_id = str(uuid.uuid4())
        # Crée un fichier réel pour tester la suppression disque
        stored_dir = tmp_path / doc_id
        stored_dir.mkdir()
        stored_file = stored_dir / "doc.md"
        stored_file.write_text("contenu")

        point = MagicMock()
        point.payload = {"stored_path": str(stored_file)}
        mock_qdrant.scroll.return_value = ([point], None)

        r = client.delete(f"{API}/documents/{doc_id}")
        assert r.status_code == 200
        assert r.json()["doc_id"] == doc_id
        mock_qdrant.delete.assert_called_once()

    def test_delete_supprime_fichier_disque(self, client, mock_qdrant, tmp_path):
        doc_id = str(uuid.uuid4())
        stored_dir = tmp_path / doc_id
        stored_dir.mkdir()
        stored_file = stored_dir / "doc.md"
        stored_file.write_text("contenu")

        point = MagicMock()
        point.payload = {"stored_path": str(stored_file)}
        mock_qdrant.scroll.return_value = ([point], None)

        client.delete(f"{API}/documents/{doc_id}")
        assert not stored_dir.exists()

    def test_delete_sans_fichier_disque_ne_plante_pas(self, client, mock_qdrant):
        """stored_path absent ou répertoire inexistant ne doit pas lever d'exception."""
        point = MagicMock()
        point.payload = {"stored_path": "/tmp/inexistant/doc.md"}
        mock_qdrant.scroll.return_value = ([point], None)

        r = client.delete(f"{API}/documents/{uuid.uuid4()}")
        assert r.status_code == 200

    def test_delete_stored_path_none_ne_plante_pas(self, client, mock_qdrant):
        point = MagicMock()
        point.payload = {}  # stored_path absent du payload
        mock_qdrant.scroll.return_value = ([point], None)

        r = client.delete(f"{API}/documents/{uuid.uuid4()}")
        assert r.status_code == 200


# ──────────────────────────────────────────────────────────────────────────────
# GET /documents/{doc_id}/download
# ──────────────────────────────────────────────────────────────────────────────


class TestDownloadDocument:
    def test_download_doc_inexistant_renvoie_404(self, client, mock_qdrant):
        mock_qdrant.scroll.return_value = ([], None)
        r = client.get(f"{API}/documents/{uuid.uuid4()}/download")
        assert r.status_code == 404

    def test_download_fichier_absent_sur_disque(self, client, mock_qdrant):
        point = MagicMock()
        point.payload = {"stored_path": "/tmp/inexistant/doc.md", "source": "doc.md"}
        mock_qdrant.scroll.return_value = ([point], None)

        r = client.get(f"{API}/documents/{uuid.uuid4()}/download")
        assert r.status_code == 404
        assert "disque" in r.json()["detail"]

    def test_download_renvoie_le_fichier(self, client, mock_qdrant, tmp_path):
        contenu = b"# Contenu du document de test"
        f = tmp_path / "doc.md"
        f.write_bytes(contenu)

        point = MagicMock()
        point.payload = {"stored_path": str(f), "source": "doc.md"}
        mock_qdrant.scroll.return_value = ([point], None)

        r = client.get(f"{API}/documents/{uuid.uuid4()}/download")
        assert r.status_code == 200
        assert r.content == contenu
        assert "attachment" in r.headers.get("content-disposition", "")


# ──────────────────────────────────────────────────────────────────────────────
# GET /documents/{job_id}/status
# ──────────────────────────────────────────────────────────────────────────────


class TestDocumentStatus:
    def test_statut_pending(self, client):
        with patch("app.api.v1.documents.AsyncResult") as mock_ar:
            mock_ar.return_value.status = "PENDING"
            r = client.get(f"{API}/documents/{uuid.uuid4()}/status")
        assert r.status_code == 200
        assert r.json()["statut"] == "PENDING"

    def test_statut_success_inclut_resultat(self, client):
        with patch("app.api.v1.documents.AsyncResult") as mock_ar:
            mock_ar.return_value.status = "SUCCESS"
            mock_ar.return_value.result = {
                "filename": "doc.md",
                "doc_id": str(uuid.uuid4()),
                "stored_path": "/storage/doc.md",
                "nb_chunks": 5,
            }
            r = client.get(f"{API}/documents/{uuid.uuid4()}/status")
        body = r.json()
        assert body["statut"] == "SUCCESS"
        assert body["resultat"]["nb_chunks"] == 5

    def test_statut_failure_inclut_erreur(self, client):
        with patch("app.api.v1.documents.AsyncResult") as mock_ar:
            mock_ar.return_value.status = "FAILURE"
            mock_ar.return_value.result = RuntimeError("Echec embedding")
            r = client.get(f"{API}/documents/{uuid.uuid4()}/status")
        body = r.json()
        assert body["statut"] == "FAILURE"
        assert "erreur" in body


# ──────────────────────────────────────────────────────────────────────────────
# Tests d'intégration (nécessitent Qdrant réel)
# ──────────────────────────────────────────────────────────────────────────────

pytestmark_integration = pytest.mark.integration


@pytest.fixture
def qdrant_doc(monkeypatch):
    """Insère des points dans Qdrant et les nettoie après le test."""
    from app.services.qdrant import COLLECTION_NAME
    from app.services.qdrant import client as real_client
    from qdrant_client.models import PointStruct, SparseVector

    doc_id = str(uuid.uuid4())
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


@pytest.mark.integration
def test_integration_list_documents(client, qdrant_doc):
    r = client.get(f"{API}/documents")
    assert r.status_code == 200
    doc_ids = [item["doc_id"] for item in r.json()["items"]]
    assert qdrant_doc in doc_ids


@pytest.mark.integration
def test_integration_get_chunks(client, qdrant_doc):
    r = client.get(f"{API}/documents/{qdrant_doc}/chunks")
    assert r.status_code == 200
    body = r.json()
    assert body["doc_id"] == qdrant_doc
    assert len(body["chunks"]) == 3
    indices = [c["chunk_index"] for c in body["chunks"]]
    assert indices == [0, 1, 2]


@pytest.mark.integration
def test_integration_delete_document(client, qdrant_doc):
    # Le doc existe
    r = client.get(f"{API}/documents/{qdrant_doc}/chunks")
    assert r.status_code == 200

    # On le supprime
    r = client.delete(f"{API}/documents/{qdrant_doc}")
    assert r.status_code == 200

    # Il n'est plus trouvable
    r = client.get(f"{API}/documents/{qdrant_doc}/chunks")
    assert r.status_code == 404


@pytest.mark.integration
def test_integration_filter_domaine(client, qdrant_doc):
    r = client.get(f"{API}/documents?domaine=IT")
    assert r.status_code == 200
    doc_ids = [item["doc_id"] for item in r.json()["items"]]
    assert qdrant_doc in doc_ids

    r = client.get(f"{API}/documents?domaine=RH")
    assert r.status_code == 200
    doc_ids_rh = [item["doc_id"] for item in r.json()["items"]]
    assert qdrant_doc not in doc_ids_rh
