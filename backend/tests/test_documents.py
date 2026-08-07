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


def _job_kwargs(mock_job) -> dict:
    """Arguments du dernier apply_async — la tâche est appelée en tout-kwargs."""
    return mock_job.apply_async.call_args.kwargs["kwargs"]


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
    from app.models.groupe import Groupe
    from app.models.user import User

    fake_admin = User(id=uuid.uuid4(), email="tester@test.local", role="ADMIN")
    # L'admin doit être membre des domaines pour pouvoir y écrire
    fake_admin.groupes = [Groupe(domaine="IT"), Groupe(domaine="RH"), Groupe(domaine="LEGAL")]
    app.dependency_overrides[get_current_user] = lambda: fake_admin

    # Session DB fictive : query(Groupe.domaine).distinct().all() → [("IT",), ("RH",), ("LEGAL",)]
    mock_db = MagicMock()
    mock_db.query.return_value.distinct.return_value.all.return_value = [("IT",), ("RH",), ("LEGAL",)]
    # ... et aucun doublon trouvé : sans ça, le MagicMock renvoyé par .first() serait
    # truthy et tout upload serait rejeté en « DÉJÀ_INDEXÉ ».
    mock_db.query.return_value.filter.return_value.first.return_value = None
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
def db_reelle(db_session):
    """Branche les routes sur la vraie base de test, avec un admin réel en base.

    Le listing, le téléchargement et la suppression lisent désormais Postgres :
    la session mock de ``_auth_override`` ne suffit plus.
    """
    from app.api.v1.documents import get_db
    from app.core.security import get_current_user
    from app.main import app
    from app.models.groupe import Groupe
    from app.models.user import User

    groupes = [Groupe(nom=f"Groupe {dom}", domaine=dom) for dom in ("IT", "RH", "LEGAL")]
    db_session.add_all(groupes)
    admin = User(email=f"{uuid.uuid4()}@test.local", role="ADMIN")
    # check_domain_write ne fait pas d'exception pour l'admin : il doit être membre
    # des domaines pour pouvoir y téléverser.
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
    """Validateur non-admin, membre du seul domaine IT.

    Sert à vérifier le contrôle de domaine sur /chunks et /download, absent jusqu'ici.
    """
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


def _doc_en_base(db, **overrides):
    """Insère une ligne `documents` prête à l'emploi."""
    from app.models.document import Document

    champs = {
        "doc_id": str(uuid.uuid4()),
        "filename": "charte.md",
        "domaine": "IT",
        "description": "",
        "nb_chunks": 3,
        "version": 1,
        "statut": "ACTIF",
    }
    champs.update(overrides)
    doc = Document(**champs)
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


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
    def test_copie_dans_le_dossier_de_version(self, tmp_path, monkeypatch):
        from app.workers.ingestion import store_file

        src = tmp_path / "source.md"
        src.write_text("contenu")
        dest_root = tmp_path / "storage"
        monkeypatch.setattr("app.workers.ingestion.settings", MagicMock(documents_storage_path=str(dest_root)))

        doc_id = str(uuid.uuid4())
        dest = store_file(str(src), doc_id, "source.md")

        assert dest == str(dest_root / doc_id / "v1" / "source.md")
        assert os.path.exists(dest)
        # Copié, pas déplacé : un retry Celery doit pouvoir relire le temporaire
        assert src.exists()

    def test_version_dans_le_chemin(self, tmp_path, monkeypatch):
        from app.workers.ingestion import store_file

        src = tmp_path / "source.md"
        src.write_text("contenu")
        dest_root = tmp_path / "storage"
        monkeypatch.setattr("app.workers.ingestion.settings", MagicMock(documents_storage_path=str(dest_root)))

        dest = store_file(str(src), "doc-42", "source.md", version=3)
        assert dest == str(dest_root / "doc-42" / "v3" / "source.md")


class TestPointId:
    def test_deterministe(self):
        from app.workers.ingestion import point_id

        assert point_id("doc-1", 1, 0) == point_id("doc-1", 1, 0)

    def test_distinct_par_version_et_index(self):
        from app.workers.ingestion import point_id

        ids = {point_id("doc-1", 1, 0), point_id("doc-1", 1, 1), point_id("doc-1", 2, 0)}
        assert len(ids) == 3


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

    def test_upload_md_valide(self, client, mock_qdrant, mock_ingestion_job):
        r = _upload(client, description="Document de test")
        assert r.status_code == 200
        body = r.json()
        assert body["statut"] == "EN_ATTENTE"
        assert body["filename"] == "doc.md"
        assert "job_id" in body

    def test_upload_pdf_valide(self, client, mock_qdrant, mock_ingestion_job):
        r = _upload(client, filename="rapport.pdf", content=_PDF_MAGIC)
        assert r.status_code == 200

    def test_description_transmise_au_job(self, client, mock_qdrant, mock_ingestion_job):
        _upload(client, description="Charte informatique 2025")
        assert _job_kwargs(mock_ingestion_job)["description"] == "Charte informatique 2025"

    def test_description_vide_par_defaut(self, client, mock_qdrant, mock_ingestion_job):
        _upload(client)
        assert _job_kwargs(mock_ingestion_job)["description"] == ""

    def test_hash_transmis_au_job(self, client, mock_qdrant, mock_ingestion_job):
        _upload(client)
        content_hash = _job_kwargs(mock_ingestion_job)["content_hash"]
        assert len(content_hash) == 64
        assert all(c in "0123456789abcdef" for c in content_hash)

    def test_job_appele_en_kwargs(self, client, mock_qdrant, mock_ingestion_job):
        """/admin/documents/{id}/retry rejoue la tâche depuis meta["kwargs"] :
        un argument positionnel y serait perdu."""
        _upload(client)
        appel = mock_ingestion_job.apply_async.call_args
        assert appel.kwargs.get("args") is None
        assert set(_job_kwargs(mock_ingestion_job)) >= {
            "file_path", "filename", "domaine", "description", "content_hash", "uploaded_by", "doc_id",
        }

    def test_doc_id_fixe_par_l_api(self, client, mock_qdrant, mock_ingestion_job):
        """doc_id doit être stable d'un retry à l'autre, donc décidé avant le job."""
        r = _upload(client)
        assert r.json()["doc_id"] == _job_kwargs(mock_ingestion_job)["doc_id"]


@pytest.mark.integration
class TestDuplicateDetection:
    """Le dédoublonnage se fait en SQL, dans le domaine visé seulement."""

    @staticmethod
    def _hash(contenu=_MD_CONTENT):
        import hashlib

        return hashlib.sha256(contenu).hexdigest()

    def test_doublon_renvoie_deja_indexe(self, client, db_reelle, mock_ingestion_job):
        doc = _doc_en_base(db_reelle, domaine="IT", filename="deja.md",
                           content_hash=self._hash(), version=2)

        body = _upload(client, domaine="IT").json()

        assert body["statut"] == "DÉJÀ_INDEXÉ"
        assert body["doc_id"] == doc.doc_id
        assert body["filename"] == "deja.md"
        assert body["version"] == 2
        assert body["job_id"] is None
        mock_ingestion_job.apply_async.assert_not_called()

    def test_contenu_different_n_est_pas_doublon(self, client, db_reelle, mock_ingestion_job):
        _doc_en_base(db_reelle, domaine="IT", content_hash=self._hash())

        r = _upload(client, domaine="IT", content=b"# Contenu unique A")

        assert r.json()["statut"] == "EN_ATTENTE"
        mock_ingestion_job.apply_async.assert_called_once()

    def test_dedoublonnage_scope_au_domaine(self, client, db_reelle, mock_ingestion_job):
        """search_hybrid filtre strictement par domaine : un document ingéré en IT est
        invisible en RH, il ne doit donc pas y interdire l'ingestion du même contenu."""
        _doc_en_base(db_reelle, domaine="IT", content_hash=self._hash())

        r = _upload(client, domaine="RH")

        assert r.json()["statut"] == "EN_ATTENTE"
        mock_ingestion_job.apply_async.assert_called_once()

    def test_document_supprime_ne_bloque_pas(self, client, db_reelle, mock_ingestion_job):
        """Le soft-delete conserve la ligne mais libère le contenu pour un ré-upload."""
        _doc_en_base(db_reelle, domaine="IT", content_hash=self._hash(), statut="SUPPRIMÉ")

        r = _upload(client, domaine="IT")

        assert r.json()["statut"] == "EN_ATTENTE"
        mock_ingestion_job.apply_async.assert_called_once()


# ──────────────────────────────────────────────────────────────────────────────
# GET /documents — listing (lu en base)
# ──────────────────────────────────────────────────────────────────────────────


def _make_point(doc_id, chunk_index=0):
    p = MagicMock()
    p.payload = {
        "doc_id": doc_id,
        "chunk_index": chunk_index,
        "contenu": f"Contenu chunk {chunk_index}",
    }
    p.id = str(uuid.uuid4())
    return p


@pytest.mark.integration
class TestListDocuments:
    def test_liste_vide(self, client, db_reelle):
        r = client.get(f"{API}/documents")
        assert r.status_code == 200
        assert r.json() == {"total": 0, "items": []}

    def test_champs_du_document(self, client, db_reelle):
        doc = _doc_en_base(db_reelle, filename="charte.md", description="Charte 2025", nb_chunks=7)

        item = client.get(f"{API}/documents").json()["items"][0]

        assert item["doc_id"] == doc.doc_id
        assert item["filename"] == "charte.md"
        assert item["description"] == "Charte 2025"
        assert item["nb_chunks"] == 7
        assert item["version"] == 1
        assert item["statut"] == "ACTIF"
        assert item["nb_versions"] == 1
        assert item["updated_at"] is not None

    def test_nb_versions_compte_les_archives(self, client, db_reelle):
        from app.models.document_version import DocumentVersion

        doc = _doc_en_base(db_reelle, version=3)
        for v in (1, 2, 3):
            db_reelle.add(DocumentVersion(doc_id=doc.doc_id, version=v, filename="charte.md"))
        db_reelle.commit()

        assert client.get(f"{API}/documents").json()["items"][0]["nb_versions"] == 3

    def test_plusieurs_docs(self, client, db_reelle):
        d1 = _doc_en_base(db_reelle, domaine="IT", nb_chunks=2)
        d2 = _doc_en_base(db_reelle, domaine="RH", nb_chunks=1)

        body = client.get(f"{API}/documents").json()

        assert body["total"] == 2
        assert {i["doc_id"]: i["nb_chunks"] for i in body["items"]} == {d1.doc_id: 2, d2.doc_id: 1}

    def test_document_supprime_absent_de_la_liste(self, client, db_reelle):
        _doc_en_base(db_reelle, statut="SUPPRIMÉ")

        assert client.get(f"{API}/documents").json()["items"] == []

    def test_filtre_domaine(self, client, db_reelle):
        _doc_en_base(db_reelle, domaine="IT")
        attendu = _doc_en_base(db_reelle, domaine="RH")

        body = client.get(f"{API}/documents?domaine=RH").json()

        assert [i["doc_id"] for i in body["items"]] == [attendu.doc_id]

    def test_filtre_domaine_inconnu_retourne_liste_vide(self, client, db_reelle):
        _doc_en_base(db_reelle, domaine="IT")

        assert client.get(f"{API}/documents?domaine=INCONNU").json()["items"] == []

    def test_filtre_domaines_multiples(self, client, db_reelle):
        _doc_en_base(db_reelle, domaine="IT")
        _doc_en_base(db_reelle, domaine="RH")
        _doc_en_base(db_reelle, domaine="LEGAL")

        body = client.get(f"{API}/documents?domaines=IT,RH").json()

        assert body["total"] == 2

    def test_ne_scrolle_plus_qdrant(self, client, db_reelle, mock_qdrant):
        """Le listing scrollait la collection entière ; il lit maintenant une table."""
        _doc_en_base(db_reelle)

        client.get(f"{API}/documents")

        mock_qdrant.scroll.assert_not_called()


# ──────────────────────────────────────────────────────────────────────────────
# GET /documents/{doc_id}/chunks
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.integration
class TestGetChunks:
    def test_chunks_tries_par_index(self, client, db_reelle, mock_qdrant):
        doc = _doc_en_base(db_reelle)
        mock_qdrant.scroll.return_value = ([_make_point(doc.doc_id, i) for i in [2, 0, 1]], None)

        body = client.get(f"{API}/documents/{doc.doc_id}/chunks").json()

        assert [c["chunk_index"] for c in body["chunks"]] == [0, 1, 2]
        assert "contenu" in body["chunks"][0]

    def test_doc_inexistant_renvoie_404(self, client, db_reelle, mock_qdrant):
        r = client.get(f"{API}/documents/{uuid.uuid4()}/chunks")
        assert r.status_code == 404

    def test_doc_supprime_renvoie_404(self, client, db_reelle, mock_qdrant):
        doc = _doc_en_base(db_reelle, statut="SUPPRIMÉ")
        r = client.get(f"{API}/documents/{doc.doc_id}/chunks")
        assert r.status_code == 404

    def test_hors_domaine_renvoie_403(self, client, db_reelle, mock_qdrant, backoffice_it):
        doc = _doc_en_base(db_reelle, domaine="RH")
        r = client.get(f"{API}/documents/{doc.doc_id}/chunks")
        assert r.status_code == 403


# ──────────────────────────────────────────────────────────────────────────────
# GET /documents/{doc_id}/download
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.integration
class TestDownloadDocument:
    def test_doc_inexistant_renvoie_404(self, client, db_reelle):
        r = client.get(f"{API}/documents/{uuid.uuid4()}/download")
        assert r.status_code == 404

    def test_fichier_absent_sur_disque(self, client, db_reelle):
        doc = _doc_en_base(db_reelle, stored_path="/tmp/inexistant/doc.md")
        r = client.get(f"{API}/documents/{doc.doc_id}/download")
        assert r.status_code == 404
        assert "disque" in r.json()["detail"]

    def test_renvoie_le_fichier(self, client, db_reelle, tmp_path):
        contenu = b"# Contenu du document de test"
        f = tmp_path / "doc.md"
        f.write_bytes(contenu)
        doc = _doc_en_base(db_reelle, filename="doc.md", stored_path=str(f))

        r = client.get(f"{API}/documents/{doc.doc_id}/download")

        assert r.status_code == 200
        assert r.content == contenu
        assert "attachment" in r.headers.get("content-disposition", "")

    def test_repli_sur_l_ancien_emplacement(self, client, db_reelle, tmp_path, monkeypatch):
        """Documents backfillés : leur fichier est resté à la racine de {doc_id}/."""
        import app.api.v1.documents as docs_module

        monkeypatch.setattr(docs_module.settings, "documents_storage_path", str(tmp_path))
        doc = _doc_en_base(db_reelle, filename="doc.md", stored_path=None)
        (tmp_path / doc.doc_id).mkdir()
        (tmp_path / doc.doc_id / "doc.md").write_bytes(b"ancien")

        r = client.get(f"{API}/documents/{doc.doc_id}/download")

        assert r.status_code == 200
        assert r.content == b"ancien"

    def test_hors_domaine_renvoie_403(self, client, db_reelle, tmp_path, backoffice_it):
        f = tmp_path / "doc.md"
        f.write_bytes(b"secret RH")
        doc = _doc_en_base(db_reelle, domaine="RH", stored_path=str(f))

        r = client.get(f"{API}/documents/{doc.doc_id}/download")

        assert r.status_code == 403


# ──────────────────────────────────────────────────────────────────────────────
# DELETE /documents/{doc_id}
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.integration
class TestDeleteDocument:
    def test_doc_inexistant_renvoie_404(self, client, db_reelle, mock_qdrant):
        r = client.delete(f"{API}/documents/{uuid.uuid4()}")
        assert r.status_code == 404

    def test_supprime_les_points_et_marque_la_ligne(self, client, db_reelle, mock_qdrant):
        doc = _doc_en_base(db_reelle)

        r = client.delete(f"{API}/documents/{doc.doc_id}")

        assert r.status_code == 200
        assert r.json()["doc_id"] == doc.doc_id
        mock_qdrant.delete.assert_called_once()
        db_reelle.refresh(doc)
        assert doc.statut == "SUPPRIMÉ"
        assert doc.deleted_at is not None
        assert doc.nb_chunks == 0

    def test_ligne_conservee_pour_la_tracabilite(self, client, db_reelle, mock_qdrant):
        """Les reponse_chunks orphelins doivent rester interprétables."""
        from app.models.document import Document

        doc = _doc_en_base(db_reelle, filename="charte.md")
        client.delete(f"{API}/documents/{doc.doc_id}")

        conserve = db_reelle.query(Document).filter(Document.doc_id == doc.doc_id).one()
        assert conserve.filename == "charte.md"

    def test_maj_en_cours_renvoie_409(self, client, db_reelle, mock_qdrant):
        doc = _doc_en_base(db_reelle, statut="EN_MAJ")

        r = client.delete(f"{API}/documents/{doc.doc_id}")

        assert r.status_code == 409
        mock_qdrant.delete.assert_not_called()

    def test_supprime_le_dossier_archives_comprises(self, client, db_reelle, mock_qdrant,
                                                    tmp_path, monkeypatch):
        """Les fichiers étant rangés par version, effacer le seul dossier de la version
        courante laisserait les archives derrière."""
        import app.api.v1.documents as docs_module

        monkeypatch.setattr(docs_module.settings, "documents_storage_path", str(tmp_path))
        doc = _doc_en_base(db_reelle)
        for v in ("v1", "v2"):
            (tmp_path / doc.doc_id / v).mkdir(parents=True)
            (tmp_path / doc.doc_id / v / "doc.md").write_text(v)
        db_reelle.commit()

        client.delete(f"{API}/documents/{doc.doc_id}")

        assert not (tmp_path / doc.doc_id).exists()

    def test_sans_fichier_disque_ne_plante_pas(self, client, db_reelle, mock_qdrant,
                                               tmp_path, monkeypatch):
        import app.api.v1.documents as docs_module

        monkeypatch.setattr(docs_module.settings, "documents_storage_path", str(tmp_path))
        doc = _doc_en_base(db_reelle)

        assert client.delete(f"{API}/documents/{doc.doc_id}").status_code == 200

    def test_deux_fois_renvoie_404(self, client, db_reelle, mock_qdrant):
        doc = _doc_en_base(db_reelle)
        client.delete(f"{API}/documents/{doc.doc_id}")

        assert client.delete(f"{API}/documents/{doc.doc_id}").status_code == 404

    def test_marque_obsoletes_les_reponses_fondees_dessus(self, client, db_reelle, mock_qdrant):
        """Tous les chunks disparaissent : aucune réponse issue de ce document ne
        peut plus être servie, sans calcul d'indices."""
        from app.models.reponse import Reponse
        from app.models.reponse_chunk import ReponseChunk
        from app.models.ticket import Ticket

        doc = _doc_en_base(db_reelle, version=3)
        ticket = Ticket(question="Q ?", domaine="IT", statut_job="TERMINÉ")
        db_reelle.add(ticket)
        db_reelle.flush()
        reponse = Reponse(ticket_id=ticket.id, contenu="R", source="LLM", statut="VALIDÉE")
        db_reelle.add(reponse)
        db_reelle.flush()
        db_reelle.add(ReponseChunk(reponse_id=reponse.id, doc_id=doc.doc_id, chunk_index=0))
        db_reelle.commit()

        r = client.delete(f"{API}/documents/{doc.doc_id}")

        assert r.json()["nb_obsoletes"] == 1
        db_reelle.refresh(reponse)
        assert reponse.obsolete is True
        assert reponse.obsolete_raison == "DOC_SUPPRIMÉ"
        assert reponse.obsolete_doc_id == doc.doc_id
        assert reponse.obsolete_version == 3


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
def qdrant_doc(db_reelle):
    """Document réel des deux côtés : ligne Postgres + points Qdrant.

    Les deux sont nécessaires depuis que la ligne `documents` fait foi : sans elle,
    `/chunks` et `DELETE` répondent 404 avant même d'interroger Qdrant.
    """
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
    from app.services.qdrant import COLLECTION_NAME
    from app.services.qdrant import client as real_client
    from qdrant_client.models import FieldCondition, Filter, MatchValue

    assert client.get(f"{API}/documents/{qdrant_doc}/chunks").status_code == 200
    assert client.get(f"{API}/documents").json()["total"] == 1

    assert client.delete(f"{API}/documents/{qdrant_doc}").status_code == 200

    # Plus dans l'index…
    restants, _ = real_client.scroll(
        collection_name=COLLECTION_NAME,
        scroll_filter=Filter(must=[FieldCondition(key="doc_id", match=MatchValue(value=qdrant_doc))]),
        limit=10,
    )
    assert restants == []
    # … ni dans la liste, mais toujours en base (soft-delete)
    assert client.get(f"{API}/documents").json()["total"] == 0
    assert client.get(f"{API}/documents/{qdrant_doc}/chunks").status_code == 404


# ──────────────────────────────────────────────────────────────────────────────
# ingestion_job — écriture des lignes documents / document_versions
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.integration
class TestEnregistrerDocument:
    """Le worker doit pouvoir rejouer son écriture en base : un retry Celery
    repasse par là avec le même doc_id."""

    @staticmethod
    def _ecrire(db, doc_id, **overrides):
        from app.workers.ingestion import _enregistrer_document

        champs = {
            "doc_id": doc_id,
            "version": 1,
            "filename": "charte.md",
            "domaine": "RH",
            "description": "Charte 2025",
            "content_hash": "a" * 64,
            "stored_path": "/tmp/inexistant/charte.md",
            "nb_chunks": 12,
            "uploaded_by": None,
        }
        champs.update(overrides)
        _enregistrer_document(db, **champs)
        db.commit()

    def test_cree_document_et_version(self, db_session):
        from app.models.document import Document
        from app.models.document_version import DocumentVersion

        doc_id = str(uuid.uuid4())
        self._ecrire(db_session, doc_id)

        doc = db_session.query(Document).filter(Document.doc_id == doc_id).one()
        assert (doc.version, doc.nb_chunks, doc.statut) == (1, 12, "ACTIF")
        assert doc.description == "Charte 2025"

        version = db_session.query(DocumentVersion).filter(DocumentVersion.doc_id == doc_id).one()
        assert version.version == 1
        assert version.nb_chunks == 12

    def test_rejouable_sans_doublon(self, db_session):
        from app.models.document import Document
        from app.models.document_version import DocumentVersion

        doc_id = str(uuid.uuid4())
        self._ecrire(db_session, doc_id)
        self._ecrire(db_session, doc_id, nb_chunks=15)

        assert db_session.query(Document).filter(Document.doc_id == doc_id).count() == 1
        assert db_session.query(DocumentVersion).filter(DocumentVersion.doc_id == doc_id).count() == 1
        assert db_session.query(Document).filter(Document.doc_id == doc_id).one().nb_chunks == 15

    def test_content_hash_vide_stocke_null(self, db_session):
        from app.models.document import Document

        doc_id = str(uuid.uuid4())
        self._ecrire(db_session, doc_id, content_hash="")

        assert db_session.query(Document).filter(Document.doc_id == doc_id).one().content_hash is None


@pytest.mark.integration
def test_integration_ingestion_job_bout_en_bout(db_session, tmp_path, monkeypatch):
    """Le job complet contre un vrai Qdrant et une vraie base — embeddings mockés.

    Vérifie ce que PR 1 apporte : ids de points déterministes, `version` et
    `stored_path` présents dès l'upsert, fichier rangé sous v1/, temporaire nettoyé,
    lignes documents/document_versions écrites.
    """
    import app.workers.ingestion as ing
    from app.models.document import Document
    from app.models.document_version import DocumentVersion
    from app.services.qdrant import COLLECTION_NAME
    from app.services.qdrant import client as real_client
    from qdrant_client.models import FieldCondition, Filter, FilterSelector, MatchValue

    monkeypatch.setattr(ing.settings, "documents_storage_path", str(tmp_path / "storage"))
    monkeypatch.setattr(ing, "chunk_text", lambda pages: ["chunk A", "chunk B"])
    monkeypatch.setattr(
        ing, "embed_texts",
        lambda textes, is_query=False: [
            {"dense": [0.1] * 1024, "sparse": {"indices": [0, 1], "values": [0.5, 0.5]}} for _ in textes
        ],
    )

    tmp_file = tmp_path / "upload.md"
    tmp_file.write_text("# Charte\n\nContenu.", encoding="utf-8")
    doc_id = str(uuid.uuid4())

    try:
        result = ing.ingestion_job.apply(kwargs={
            "file_path": str(tmp_file),
            "filename": "charte.md",
            "domaine": "RH",
            "description": "Charte 2025",
            "content_hash": "b" * 64,
            "uploaded_by": None,
            "doc_id": doc_id,
        }).get()

        assert result["statut"] == "OK"
        assert result["doc_id"] == doc_id
        assert result["nb_chunks"] == 2

        # Fichier rangé par version, temporaire nettoyé
        attendu = tmp_path / "storage" / doc_id / "v1" / "charte.md"
        assert attendu.is_file()
        assert not tmp_file.exists()

        # Points Qdrant : ids déterministes, version et stored_path dès l'upsert
        points, _ = real_client.scroll(
            collection_name=COLLECTION_NAME,
            scroll_filter=Filter(must=[FieldCondition(key="doc_id", match=MatchValue(value=doc_id))]),
            with_payload=True,
            limit=10,
        )
        assert len(points) == 2
        assert {str(p.id) for p in points} == {ing.point_id(doc_id, 1, 0), ing.point_id(doc_id, 1, 1)}
        for p in points:
            assert p.payload["version"] == 1
            assert p.payload["stored_path"] == str(attendu)

        # Lignes en base
        doc = db_session.query(Document).filter(Document.doc_id == doc_id).one()
        assert (doc.version, doc.domaine, doc.nb_chunks, doc.statut) == (1, "RH", 2, "ACTIF")
        version = db_session.query(DocumentVersion).filter(DocumentVersion.doc_id == doc_id).one()
        assert version.stored_path == str(attendu)
        assert version.taille_octets == attendu.stat().st_size
    finally:
        real_client.delete(
            collection_name=COLLECTION_NAME,
            points_selector=FilterSelector(
                filter=Filter(must=[FieldCondition(key="doc_id", match=MatchValue(value=doc_id))])
            ),
        )
