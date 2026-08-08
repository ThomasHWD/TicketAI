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
from types import SimpleNamespace
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


def _upload(client, *, domaine="IT", filename="doc.md", content=_MD_CONTENT, content_type="text/plain",
            description="", force_nouveau=False):
    """Helper qui poste un fichier vers POST /documents."""
    params = f"domaine={domaine}"
    if description:
        params += f"&description={description}"
    if force_nouveau:
        params += "&force_nouveau=true"
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


@pytest.fixture
def admin_sans_groupe(db_reelle):
    """Administrateur membre d'aucun domaine.

    La fixture ``db_reelle`` inscrit son admin dans les trois domaines, ce qui
    masque entièrement le contrôle d'écriture. Celui-ci sert à vérifier ce que
    l'admin ne peut *pas* faire : `check_domain_write` ne l'exempte pas.
    """
    from app.core.security import get_current_user
    from app.main import app
    from app.models.user import User

    user = User(email=f"{uuid.uuid4()}@test.local", role="ADMIN")
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


@pytest.mark.integration
class TestGardeFouHomonyme:
    """Même nom + même domaine + contenu différent = très probablement une v2.

    Sans ce garde-fou, l'ingestion créait un second document indépendant et les
    deux versions répondaient tour à tour, en se contredisant.
    """

    def test_409_avec_detail_structure(self, client, db_reelle, mock_ingestion_job):
        """Le `detail` est un dict, pas un message : le front en tire le doc_id à mettre à jour."""
        doc = _doc_en_base(db_reelle, domaine="IT", filename="charte.md", nb_chunks=7, version=3)

        r = _upload(client, domaine="IT", filename="charte.md", content=b"# Contenu different")

        assert r.status_code == 409
        assert r.json()["detail"] == {
            "code": "DOCUMENT_HOMONYME",
            "doc_id": doc.doc_id,
            "filename": "charte.md",
            "domaine": "IT",
            "version": 3,
            "nb_chunks": 7,
        }
        mock_ingestion_job.apply_async.assert_not_called()

    def test_force_nouveau_passe(self, client, db_reelle, mock_ingestion_job):
        _doc_en_base(db_reelle, domaine="IT", filename="charte.md")

        r = _upload(client, domaine="IT", filename="charte.md",
                    content=b"# Contenu different", force_nouveau=True)

        assert r.json()["statut"] == "EN_ATTENTE"
        mock_ingestion_job.apply_async.assert_called_once()

    def test_ignore_les_supprimes(self, client, db_reelle, mock_ingestion_job):
        _doc_en_base(db_reelle, domaine="IT", filename="charte.md", statut="SUPPRIMÉ")

        r = _upload(client, domaine="IT", filename="charte.md", content=b"# Contenu different")

        assert r.json()["statut"] == "EN_ATTENTE"

    def test_scope_au_domaine(self, client, db_reelle, mock_ingestion_job):
        """Deux domaines cloisonnés peuvent légitimement avoir chacun leur « charte.md »."""
        _doc_en_base(db_reelle, domaine="IT", filename="charte.md")

        r = _upload(client, domaine="RH", filename="charte.md", content=b"# Contenu different")

        assert r.json()["statut"] == "EN_ATTENTE"

    def test_le_hash_identique_prime_sur_le_nom(self, client, db_reelle, mock_ingestion_job):
        """Même nom ET même contenu : il n'y a rien à mettre à jour, donc pas de 409."""
        import hashlib

        _doc_en_base(db_reelle, domaine="IT", filename="charte.md",
                     content_hash=hashlib.sha256(_MD_CONTENT).hexdigest())

        r = _upload(client, domaine="IT", filename="charte.md")

        assert r.status_code == 200
        assert r.json()["statut"] == "DÉJÀ_INDEXÉ"


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

    def test_hors_domaine_renvoie_403(self, client, db_reelle, backoffice_it, mock_qdrant):
        doc = _doc_en_base(db_reelle, domaine="RH")

        r = client.delete(f"{API}/documents/{doc.doc_id}")

        assert r.status_code == 403
        mock_qdrant.delete.assert_not_called()

    def test_admin_hors_domaine_renvoie_403(self, client, db_reelle, admin_sans_groupe, mock_qdrant):
        """Le rôle ne donne rien ici : supprimer un document, c'est agir sur un
        domaine, et `check_domain_write` n'exempte pas l'administrateur."""
        doc = _doc_en_base(db_reelle, domaine="RH")

        r = client.delete(f"{API}/documents/{doc.doc_id}")

        assert r.status_code == 403
        mock_qdrant.delete.assert_not_called()

    def test_par_le_domaine_ok_sans_etre_admin(self, client, db_reelle, backoffice_it, mock_qdrant):
        """Le pendant : celui qui peut remplacer le fichier peut aussi le supprimer."""
        doc = _doc_en_base(db_reelle, domaine="IT")

        r = client.delete(f"{API}/documents/{doc.doc_id}")

        assert r.status_code == 200

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
# POST /documents/{doc_id}/versions/preview et /confirm
# ──────────────────────────────────────────────────────────────────────────────

_TEXTE_V1 = (
    b"Le teletravail est limite a 2 jours par semaine, sur accord du manager.\n\n"
    b"La demande se fait via le portail RH, au moins 5 jours ouvres a l'avance."
)
_TEXTE_V2 = _TEXTE_V1.replace(b"2 jours", b"3 jours")


@pytest.fixture
def qdrant_maj(monkeypatch):
    """L'aperçu capture les chunks via `document_update.client`, pas celui du routeur."""
    import app.workers.document_update as maj_module

    mock = MagicMock()
    mock.scroll.return_value = (
        [
            SimpleNamespace(payload={"chunk_index": i, "contenu": t.decode()})
            for i, t in enumerate(_TEXTE_V1.split(b"\n\n"))
        ],
        None,
    )
    monkeypatch.setattr(maj_module, "client", mock)
    return mock


@pytest.fixture
def mock_maj_job(monkeypatch):
    import app.api.v1.documents as docs_module

    mock_job = MagicMock()
    mock_task = MagicMock()
    mock_task.id = str(uuid.uuid4())
    mock_job.apply_async.return_value = mock_task
    monkeypatch.setattr(docs_module, "document_update_job", mock_job)
    return mock_job


@pytest.fixture
def staging_tmp(tmp_path, monkeypatch):
    import app.api.v1.documents as docs_module

    monkeypatch.setattr(docs_module, "STAGING_DIR", str(tmp_path / "staging"))
    return tmp_path


def _preview(client, doc_id, content=_TEXTE_V2, filename="charte.md"):
    return client.post(
        f"{API}/documents/{doc_id}/versions/preview",
        files={"file": (filename, io.BytesIO(content), "text/plain")},
    )


@pytest.mark.integration
class TestPreviewMaj:
    def test_404_document_inconnu(self, client, db_reelle, staging_tmp, qdrant_maj):
        assert _preview(client, str(uuid.uuid4())).status_code == 404

    def test_403_hors_domaine(self, client, db_reelle, backoffice_it, staging_tmp, qdrant_maj):
        doc = _doc_en_base(db_reelle, domaine="RH", content_hash="hash-v1")

        assert _preview(client, doc.doc_id).status_code == 403

    def test_409_si_maj_en_cours(self, client, db_reelle, staging_tmp, qdrant_maj):
        from datetime import datetime, timezone

        doc = _doc_en_base(
            db_reelle, content_hash="hash-v1", statut="EN_MAJ",
            update_started_at=datetime.now(timezone.utc),
        )

        r = _preview(client, doc.doc_id)

        assert r.status_code == 409
        assert "en cours" in r.json()["detail"]

    def test_verrou_perime_ne_bloque_plus(self, client, db_reelle, staging_tmp, qdrant_maj):
        """Un worker tué net n'exécute pas `on_failure` : sans péremption, le
        document resterait verrouillé à vie."""
        from datetime import datetime, timedelta, timezone

        doc = _doc_en_base(
            db_reelle, content_hash="hash-v1", statut="EN_MAJ",
            update_started_at=datetime.now(timezone.utc) - timedelta(hours=2),
        )

        assert _preview(client, doc.doc_id).status_code == 200

    def test_409_fichier_identique(self, client, db_reelle, staging_tmp, qdrant_maj):
        import hashlib

        doc = _doc_en_base(db_reelle, content_hash=hashlib.sha256(_TEXTE_V2).hexdigest())

        r = _preview(client, doc.doc_id)

        assert r.status_code == 409
        assert "identique" in r.json()["detail"]

    def test_hash_null_autorise_et_renseigne(self, client, db_reelle, staging_tmp, qdrant_maj):
        """Document backfillé : on ne peut pas prouver l'identité, donc on ne
        l'interdit pas — et on en profite pour renseigner le hash manquant."""
        doc = _doc_en_base(db_reelle, content_hash=None)

        assert _preview(client, doc.doc_id).status_code == 200

        db_reelle.refresh(doc)
        assert doc.content_hash is not None

    def test_409_contenu_deja_indexe_ailleurs(self, client, db_reelle, staging_tmp, qdrant_maj):
        import hashlib

        doc = _doc_en_base(db_reelle, content_hash="hash-v1")
        _doc_en_base(db_reelle, filename="autre.md", content_hash=hashlib.sha256(_TEXTE_V2).hexdigest())

        r = _preview(client, doc.doc_id)

        assert r.status_code == 409
        assert "autre.md" in r.json()["detail"]

    def test_impact_exact(self, client, db_reelle, staging_tmp, qdrant_maj):
        """L'aperçu doit nommer les réponses, pas les estimer : annoncer 12
        impactées puis n'en supprimer que 2 serait pire qu'inutile."""
        doc = _doc_en_base(db_reelle, domaine="RH", content_hash="hash-v1")
        reponse = _reponse_sur_chunk(db_reelle, doc.doc_id, chunk_index=0, domaine="RH")

        body = _preview(client, doc.doc_id).json()

        assert body["version_cible"] == 2
        assert body["nb_total_chunks"] == 2
        assert body["nb_chunks_modifies"] == 1
        assert body["nb_obsoletes"] == 1
        assert body["nb_canoniques"] == 1
        item = body["items"][0]
        assert item["reponse_id"] == str(reponse.id)
        assert item["chunks_modifies"] == [0]
        assert "2 jours" in item["extraits"][0]

    def test_ne_modifie_rien(self, client, db_reelle, staging_tmp, qdrant_maj, mock_maj_job):
        from app.models.document import Document

        doc = _doc_en_base(db_reelle, domaine="RH", content_hash="hash-v1")
        reponse = _reponse_sur_chunk(db_reelle, doc.doc_id, chunk_index=0, domaine="RH")

        _preview(client, doc.doc_id)

        db_reelle.refresh(reponse)
        db_reelle.refresh(doc)
        assert reponse.obsolete is False
        assert doc.statut == "ACTIF"
        assert db_reelle.query(Document).filter(Document.doc_id == doc.doc_id).first().version == 1
        mock_maj_job.apply_async.assert_not_called()

    def test_passage_intact_zero_obsolete(self, client, db_reelle, staging_tmp, qdrant_maj):
        doc = _doc_en_base(db_reelle, domaine="RH", content_hash="hash-v1")
        _reponse_sur_chunk(db_reelle, doc.doc_id, chunk_index=1, domaine="RH")

        body = _preview(client, doc.doc_id).json()

        assert body["nb_chunks_modifies"] == 1
        assert body["nb_obsoletes"] == 0

    def test_purge_les_apercus_expires(self, client, db_reelle, staging_tmp, qdrant_maj):
        from datetime import datetime, timedelta, timezone

        from app.models.document_staging import DocumentStaging

        doc = _doc_en_base(db_reelle, content_hash="hash-v1")
        vieux_fichier = staging_tmp / "abandonne.md"
        vieux_fichier.write_bytes(_TEXTE_V1)
        db_reelle.add(
            DocumentStaging(
                doc_id=doc.doc_id, stored_path=str(vieux_fichier), filename="abandonne.md",
                expires_at=datetime.now(timezone.utc) - timedelta(hours=2),
            )
        )
        db_reelle.commit()

        _preview(client, doc.doc_id)

        assert not vieux_fichier.exists()
        assert db_reelle.query(DocumentStaging).filter(
            DocumentStaging.filename == "abandonne.md"
        ).first() is None


_ARTICLE_AJOUTE = (
    b"Article 7 bis : le teletravail est suspendu pendant les periodes de forte activite."
)

_ARTICLE_ABROGE = (
    b"Article 9 : une prime de 20 euros par mois compense les frais d'electricite du domicile."
)


def _doc_avec_fichier(db, tmp_path, contenu=_TEXTE_V1, **overrides):
    """Document dont le fichier de la version courante existe vraiment sur disque.

    C'est la condition de l'analyse des ajouts : sans ce fichier, il n'y a pas de
    texte de référence à comparer.
    """
    chemin = tmp_path / "courant.md"
    chemin.write_bytes(contenu)
    return _doc_en_base(
        db, domaine="RH", content_hash="hash-v1", stored_path=str(chemin), **overrides
    )


@pytest.mark.integration
class TestAjoutsSignales:
    """Le miroir de l'obsolescence : ce que la nouvelle version dit de neuf.

    Rien n'en devient obsolète — l'ajout n'invalide pas mécaniquement une réponse,
    seule une lecture humaine peut trancher. L'aperçu se contente de le rendre
    visible, faute de quoi une charte enrichie d'un « article 7 bis » laisserait
    les réponses existantes continuer d'être servies sans que personne ne le sache.
    """

    def test_signale_un_ajout_qui_ne_rend_rien_obsolete(self, client, db_reelle, staging_tmp, qdrant_maj):
        doc = _doc_avec_fichier(db_reelle, staging_tmp)
        _reponse_sur_chunk(db_reelle, doc.doc_id, chunk_index=0, domaine="RH")

        body = _preview(client, doc.doc_id, content=_TEXTE_V1 + b"\n\n" + _ARTICLE_AJOUTE).json()

        # Aucun passage cité n'a bougé : la détection d'obsolescence est muette,
        # et c'est précisément le trou que ce panneau vient combler.
        assert body["nb_chunks_modifies"] == 0
        assert body["nb_obsoletes"] == 0
        assert body["ajouts_analysables"] is True
        assert body["nb_passages_ajoutes"] == 1
        assert "Article 7 bis" in body["extraits_ajoutes"][0]
        assert body["nb_a_relire"] == 1

    def test_nomme_les_reponses_a_relire(self, client, db_reelle, staging_tmp, qdrant_maj):
        """Un compte seul n'est pas actionnable : « 4 réponses n'en tiennent pas
        compte » oblige à les retrouver à la main, donc personne ne le fait.
        L'aperçu doit livrer de quoi ouvrir chacune, `ticket_id` compris."""
        doc = _doc_avec_fichier(db_reelle, staging_tmp)
        reponse = _reponse_sur_chunk(db_reelle, doc.doc_id, chunk_index=0, domaine="RH")

        body = _preview(client, doc.doc_id, content=_TEXTE_V1 + b"\n\n" + _ARTICLE_AJOUTE).json()

        assert body["nb_a_relire"] == 1
        [item] = body["a_relire"]
        assert item["reponse_id"] == str(reponse.id)
        assert item["ticket_id"] == str(reponse.ticket_id)
        assert item["question"] == "Combien de jours de télétravail ?"
        assert item["canonique"] is True
        assert item["nb_validations"] == 3

    def test_les_plus_servies_en_tete(self, client, db_reelle, staging_tmp, qdrant_maj):
        """Une canonique à 12 validations part sur tous les tickets similaires ;
        une VALIDÉE isolée ne ressort presque jamais. L'ordre de relecture doit
        suivre le risque réel, pas l'ordre d'insertion en base."""
        doc = _doc_avec_fichier(db_reelle, staging_tmp)
        _reponse_sur_chunk(db_reelle, doc.doc_id, chunk_index=0, domaine="RH", nb_validations=1)
        forte = _reponse_sur_chunk(db_reelle, doc.doc_id, chunk_index=1, domaine="RH", nb_validations=12)

        body = _preview(client, doc.doc_id, content=_TEXTE_V1 + b"\n\n" + _ARTICLE_AJOUTE).json()

        assert [i["nb_validations"] for i in body["a_relire"]] == [12, 1]
        assert body["a_relire"][0]["reponse_id"] == str(forte.id)

    def test_plafonne_la_liste_sans_fausser_le_compte(self, client, db_reelle, staging_tmp, qdrant_maj):
        """La modale amorce le tri, elle ne le porte pas. Mais tronquer le *compte*
        minimiserait la charge annoncée : seule la liste est plafonnée."""
        doc = _doc_avec_fichier(db_reelle, staging_tmp)
        for _ in range(12):
            _reponse_sur_chunk(db_reelle, doc.doc_id, chunk_index=0, domaine="RH")

        body = _preview(client, doc.doc_id, content=_TEXTE_V1 + b"\n\n" + _ARTICLE_AJOUTE).json()

        assert body["nb_a_relire"] == 12
        assert len(body["a_relire"]) == 10

    def test_aucun_ajout_sur_un_simple_reformatage(self, client, db_reelle, staging_tmp, qdrant_maj):
        """Le panneau doit rester silencieux quand rien n'a été écrit : sinon il
        s'affiche à chaque mise à jour et cesse d'être lu."""
        doc = _doc_avec_fichier(db_reelle, staging_tmp)
        reformate = _TEXTE_V1.replace(b"\n\n", b"\n\n\n").replace(b" par ", b"  par ")

        body = _preview(client, doc.doc_id, content=reformate).json()

        assert body["ajouts_analysables"] is True
        assert body["nb_passages_ajoutes"] == 0
        assert body["extraits_ajoutes"] == []

    def test_ne_compte_pas_les_reponses_qui_vont_disparaitre(self, client, db_reelle, staging_tmp, qdrant_maj):
        """Une réponse déjà condamnée n'est pas « à relire » : elle ne sera plus
        servie du tout. La compter deux fois exagérerait la charge annoncée."""
        doc = _doc_avec_fichier(db_reelle, staging_tmp)
        _reponse_sur_chunk(db_reelle, doc.doc_id, chunk_index=0, domaine="RH")  # devient obsolète
        _reponse_sur_chunk(db_reelle, doc.doc_id, chunk_index=1, domaine="RH")  # reste servie

        body = _preview(client, doc.doc_id, content=_TEXTE_V2 + b"\n\n" + _ARTICLE_AJOUTE).json()

        assert body["nb_obsoletes"] == 1
        assert body["nb_passages_ajoutes"] >= 1
        assert body["nb_a_relire"] == 1

    def test_document_backfille_tait_le_panneau(self, client, db_reelle, staging_tmp, qdrant_maj):
        """Sans fichier courant sur disque, il n'y a rien à comparer. Renvoyer
        « 0 passage ajouté » se lirait comme une garantie ; on ne dit rien."""
        doc = _doc_en_base(db_reelle, domaine="RH", content_hash="hash-v1", stored_path=None)
        _reponse_sur_chunk(db_reelle, doc.doc_id, chunk_index=0, domaine="RH")

        body = _preview(client, doc.doc_id, content=_TEXTE_V1 + b"\n\n" + _ARTICLE_AJOUTE).json()

        assert body["ajouts_analysables"] is False
        assert body["nb_passages_ajoutes"] == 0
        assert body["nb_a_relire"] == 0

    def test_archive_illisible_ne_fait_pas_echouer_l_apercu(self, client, db_reelle, staging_tmp, qdrant_maj):
        """L'obsolescence, elle, est déjà calculée : perdre le signal secondaire ne
        doit pas coûter le signal principal."""
        corrompu = staging_tmp / "corrompu.pdf"
        corrompu.write_bytes(b"%PDF-1.4 ceci n'est pas un PDF")
        doc = _doc_en_base(
            db_reelle, domaine="RH", content_hash="hash-v1", stored_path=str(corrompu)
        )
        _reponse_sur_chunk(db_reelle, doc.doc_id, chunk_index=0, domaine="RH")

        r = _preview(client, doc.doc_id)

        assert r.status_code == 200
        assert r.json()["nb_obsoletes"] == 1
        assert r.json()["ajouts_analysables"] is False


@pytest.mark.integration
class TestRetraitsSignales:
    """L'autre sens : ce que la nouvelle version ne dit plus.

    Le seul cas qu'un compte d'ajouts ne peut pas voir — une règle **abrogée**
    sans que rien ne soit inséré à la place. Aucun passage cité ne bouge, aucun
    passage n'apparaît, et pourtant une réponse qui s'appuyait sur l'existence de
    cette règle est peut-être devenue fausse.
    """

    def test_signale_un_passage_retire_ailleurs(self, client, db_reelle, staging_tmp, qdrant_maj):
        doc = _doc_avec_fichier(db_reelle, staging_tmp, contenu=_TEXTE_V1 + b"\n\n" + _ARTICLE_ABROGE)
        _reponse_sur_chunk(db_reelle, doc.doc_id, chunk_index=0, domaine="RH")

        body = _preview(client, doc.doc_id, content=_TEXTE_V1).json()

        # Les deux passages cités sont intacts : sans le second sens, l'aperçu
        # annoncerait un document strictement inchangé.
        assert body["nb_chunks_modifies"] == 0
        assert body["nb_obsoletes"] == 0
        assert body["nb_passages_ajoutes"] == 0
        assert body["nb_passages_retires"] == 1
        assert "Article 9" in body["extraits_retires"][0]
        assert body["nb_a_relire"] == 1

    def test_reformatage_ne_tire_dans_aucun_sens(self, client, db_reelle, staging_tmp, qdrant_maj):
        """La propriété anti-inondation, vérifiée sur les deux sens à la fois :
        un second compteur toujours non nul rendrait le panneau permanent."""
        doc = _doc_avec_fichier(db_reelle, staging_tmp)
        reformate = _TEXTE_V1.replace(b"\n\n", b"\n\n\n").replace(b" par ", b"  par ")

        body = _preview(client, doc.doc_id, content=reformate).json()

        assert body["nb_passages_ajoutes"] == 0
        assert body["nb_passages_retires"] == 0
        assert body["extraits_retires"] == []
        assert body["nb_a_relire"] == 0

    def test_document_backfille_tait_les_deux_sens(self, client, db_reelle, staging_tmp, qdrant_maj):
        doc = _doc_en_base(db_reelle, domaine="RH", content_hash="hash-v1", stored_path=None)
        _reponse_sur_chunk(db_reelle, doc.doc_id, chunk_index=0, domaine="RH")

        body = _preview(client, doc.doc_id, content=_TEXTE_V1).json()

        assert body["ajouts_analysables"] is False
        assert body["nb_passages_retires"] == 0
        assert body["extraits_retires"] == []


@pytest.mark.integration
class TestConfirmMaj:
    def test_lance_le_job_et_pose_le_verrou(self, client, db_reelle, staging_tmp, qdrant_maj, mock_maj_job):
        doc = _doc_en_base(db_reelle, domaine="RH", content_hash="hash-v1")
        staging_id = _preview(client, doc.doc_id).json()["staging_id"]

        r = client.post(
            f"{API}/documents/{doc.doc_id}/versions/confirm", json={"staging_id": staging_id}
        )

        body = r.json()
        assert r.status_code == 200
        # Même forme que l'upload : le suivi de job du front fonctionne sans adaptation
        assert set(body) == {"job_id", "doc_id", "filename", "version", "statut"}
        assert body["version"] == 2
        assert body["statut"] == "EN_ATTENTE"

        db_reelle.refresh(doc)
        assert doc.statut == "EN_MAJ"
        assert doc.update_job_id == body["job_id"]

        envoyes = mock_maj_job.apply_async.call_args.kwargs["kwargs"]
        assert envoyes["new_version"] == 2
        assert envoyes["doc_id"] == doc.doc_id
        assert os.path.isfile(envoyes["file_path"])

    def test_consomme_l_apercu(self, client, db_reelle, staging_tmp, qdrant_maj, mock_maj_job):
        """Rejouer la même confirmation ne doit pas relancer un second job."""
        from app.models.document_staging import DocumentStaging

        doc = _doc_en_base(db_reelle, domaine="RH", content_hash="hash-v1")
        staging_id = _preview(client, doc.doc_id).json()["staging_id"]
        client.post(f"{API}/documents/{doc.doc_id}/versions/confirm", json={"staging_id": staging_id})

        assert db_reelle.query(DocumentStaging).count() == 0

    def test_404_apercu_inconnu(self, client, db_reelle, staging_tmp, qdrant_maj, mock_maj_job):
        doc = _doc_en_base(db_reelle, content_hash="hash-v1")

        r = client.post(
            f"{API}/documents/{doc.doc_id}/versions/confirm", json={"staging_id": str(uuid.uuid4())}
        )

        assert r.status_code == 404

    def test_403_apercu_d_un_autre_utilisateur(self, client, db_reelle, staging_tmp, qdrant_maj, mock_maj_job):
        from datetime import datetime, timedelta, timezone

        from app.models.document_staging import DocumentStaging
        from app.models.user import User

        doc = _doc_en_base(db_reelle, content_hash="hash-v1")
        autre = User(email=f"{uuid.uuid4()}@test.local", role="ADMIN")
        db_reelle.add(autre)
        db_reelle.commit()
        staging = DocumentStaging(
            doc_id=doc.doc_id, user_id=autre.id, stored_path=str(staging_tmp / "x.md"),
            filename="x.md", expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        db_reelle.add(staging)
        db_reelle.commit()

        r = client.post(
            f"{API}/documents/{doc.doc_id}/versions/confirm", json={"staging_id": str(staging.id)}
        )

        assert r.status_code == 403

    def test_409_apercu_expire(self, client, db_reelle, staging_tmp, qdrant_maj, mock_maj_job):
        from datetime import datetime, timedelta, timezone

        from app.models.document_staging import DocumentStaging

        doc = _doc_en_base(db_reelle, content_hash="hash-v1")
        fichier = staging_tmp / "expire.md"
        fichier.write_bytes(_TEXTE_V2)
        staging = DocumentStaging(
            doc_id=doc.doc_id, user_id=_admin_id(db_reelle),
            stored_path=str(fichier), filename="expire.md",
            expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        )
        db_reelle.add(staging)
        db_reelle.commit()

        r = client.post(
            f"{API}/documents/{doc.doc_id}/versions/confirm", json={"staging_id": str(staging.id)}
        )

        assert r.status_code == 409
        assert "expiré" in r.json()["detail"]


def _admin_id(db):
    from app.models.user import User

    return db.query(User).filter(User.role == "ADMIN").first().id


def _reponse_sur_chunk(db, doc_id, *, chunk_index, domaine="IT", nb_validations=3):
    """Réponse canonique validée s'appuyant sur un chunk précis du document."""
    from app.models.reponse import Reponse
    from app.models.reponse_chunk import ReponseChunk
    from app.models.ticket import Ticket

    ticket = Ticket(question="Combien de jours de télétravail ?", domaine=domaine, statut_job="TERMINÉ")
    db.add(ticket)
    db.flush()
    reponse = Reponse(
        ticket_id=ticket.id, contenu="Deux jours.", source="LLM", statut="VALIDÉE",
        canonique=True, nb_validations=nb_validations,
    )
    db.add(reponse)
    db.flush()
    db.add(ReponseChunk(reponse_id=reponse.id, doc_id=doc_id, chunk_index=chunk_index))
    db.commit()
    return reponse


# ──────────────────────────────────────────────────────────────────────────────
# Historique des versions
# ──────────────────────────────────────────────────────────────────────────────


def _version_en_base(db, doc, version, *, contenu=_TEXTE_V1, racine=None, **overrides):
    """Insère une ligne `document_versions`, avec son fichier archivé sur disque."""
    from app.models.document_version import DocumentVersion

    chemin = None
    if racine is not None:
        dossier = os.path.join(str(racine), doc.doc_id, f"v{version}")
        os.makedirs(dossier, exist_ok=True)
        chemin = os.path.join(dossier, doc.filename)
        with open(chemin, "wb") as f:
            f.write(contenu)

    champs = {
        "doc_id": doc.doc_id,
        "version": version,
        "filename": doc.filename,
        "stored_path": chemin,
        "nb_chunks": 2,
        "taille_octets": len(contenu),
    }
    champs.update(overrides)
    v = DocumentVersion(**champs)
    db.add(v)
    db.commit()
    db.refresh(v)
    return v


@pytest.mark.integration
class TestListerVersions:
    def test_liste_decroissante_avec_la_courante_marquee(self, client, db_reelle, tmp_path):
        doc = _doc_en_base(db_reelle, version=2)
        _version_en_base(db_reelle, doc, 1, racine=tmp_path)
        _version_en_base(db_reelle, doc, 2, racine=tmp_path, restauree_depuis=1)

        body = client.get(f"{API}/documents/{doc.doc_id}/versions").json()

        assert body["version_courante"] == 2
        assert [v["version"] for v in body["items"]] == [2, 1]
        assert [v["courante"] for v in body["items"]] == [True, False]
        assert body["items"][0]["restauree_depuis"] == 1

    def test_signale_un_fichier_archive_manquant(self, client, db_reelle, tmp_path, monkeypatch):
        """Sans ce drapeau, l'UI proposerait un téléchargement voué au 404."""
        import app.api.v1.documents as docs_module

        monkeypatch.setattr(docs_module.settings, "documents_storage_path", str(tmp_path))
        doc = _doc_en_base(db_reelle)
        _version_en_base(db_reelle, doc, 1, stored_path="/introuvable/charte.md")

        body = client.get(f"{API}/documents/{doc.doc_id}/versions").json()

        assert body["items"][0]["fichier_disponible"] is False

    def test_403_hors_domaine(self, client, db_reelle, backoffice_it):
        doc = _doc_en_base(db_reelle, domaine="RH")

        assert client.get(f"{API}/documents/{doc.doc_id}/versions").status_code == 403


@pytest.mark.integration
class TestTelechargerVersion:
    def test_renvoie_le_fichier_archive(self, client, db_reelle, tmp_path):
        doc = _doc_en_base(db_reelle, version=2)
        _version_en_base(db_reelle, doc, 1, contenu=_TEXTE_V1, racine=tmp_path)
        _version_en_base(db_reelle, doc, 2, contenu=_TEXTE_V2, racine=tmp_path)

        r = client.get(f"{API}/documents/{doc.doc_id}/versions/1/download")

        assert r.status_code == 200
        assert r.content == _TEXTE_V1

    def test_404_version_inconnue(self, client, db_reelle):
        doc = _doc_en_base(db_reelle)

        assert client.get(f"{API}/documents/{doc.doc_id}/versions/9/download").status_code == 404


@pytest.mark.integration
class TestRestaurerVersion:
    """Restaurer emprunte le flux de mise à jour : aperçu d'impact, puis `confirm`."""

    def test_apercu_avec_restauree_depuis(self, client, db_reelle, tmp_path, staging_tmp, qdrant_maj):
        # La v1 (texte de référence de `qdrant_maj`) est restaurée par-dessus une v2
        # dont le contenu diffère : rien ne doit avoir disparu du document.
        doc = _doc_en_base(db_reelle, version=2, content_hash="hash-v2")
        _version_en_base(db_reelle, doc, 1, contenu=_TEXTE_V1, racine=tmp_path, content_hash="hash-v1")
        _version_en_base(db_reelle, doc, 2, contenu=_TEXTE_V2, racine=tmp_path, content_hash="hash-v2")

        body = client.post(f"{API}/documents/{doc.doc_id}/versions/1/restaurer").json()

        assert body["restauree_depuis"] == 1
        # Restaurer ne rembobine pas : la version restaurée se pose au-dessus.
        assert body["version_cible"] == 3
        assert body["nb_chunks_modifies"] == 0
        assert body["nb_obsoletes"] == 0

    def test_impact_calcule_comme_une_maj(self, client, db_reelle, tmp_path, staging_tmp, qdrant_maj):
        """Restaurer peut à son tour rendre des réponses obsolètes — c'est le point."""
        doc = _doc_en_base(db_reelle, version=2, content_hash="hash-v2")
        _reponse_sur_chunk(db_reelle, doc.doc_id, chunk_index=0)
        # Le fichier archivé ne contient plus le passage qui fondait la réponse.
        _version_en_base(db_reelle, doc, 1, contenu=b"Texte totalement different.",
                         racine=tmp_path, content_hash="hash-v1")

        body = client.post(f"{API}/documents/{doc.doc_id}/versions/1/restaurer").json()

        assert body["nb_obsoletes"] == 1
        assert body["items"][0]["chunks_modifies"] == [0]

    def test_la_confirmation_transmet_restauree_depuis(
        self, client, db_reelle, tmp_path, staging_tmp, qdrant_maj, mock_maj_job
    ):
        doc = _doc_en_base(db_reelle, version=2, content_hash="hash-v2")
        _version_en_base(db_reelle, doc, 1, racine=tmp_path, content_hash="hash-v1")
        staging_id = client.post(
            f"{API}/documents/{doc.doc_id}/versions/1/restaurer"
        ).json()["staging_id"]

        client.post(f"{API}/documents/{doc.doc_id}/versions/confirm", json={"staging_id": staging_id})

        assert mock_maj_job.apply_async.call_args.kwargs["kwargs"]["restauree_depuis"] == 1

    def test_409_version_courante(self, client, db_reelle, tmp_path, staging_tmp, qdrant_maj):
        doc = _doc_en_base(db_reelle, version=2)
        _version_en_base(db_reelle, doc, 2, racine=tmp_path)

        r = client.post(f"{API}/documents/{doc.doc_id}/versions/2/restaurer")

        assert r.status_code == 409
        assert "déjà la version actuelle" in r.json()["detail"]

    def test_409_contenu_identique_a_la_courante(self, client, db_reelle, tmp_path, staging_tmp, qdrant_maj):
        """Numéro différent, contenu identique : la restauration n'apporterait rien."""
        doc = _doc_en_base(db_reelle, version=2, content_hash="hash-commun")
        _version_en_base(db_reelle, doc, 1, racine=tmp_path, content_hash="hash-commun")

        r = client.post(f"{API}/documents/{doc.doc_id}/versions/1/restaurer")

        assert r.status_code == 409
        assert "même contenu" in r.json()["detail"]

    def test_409_fichier_archive_absent(self, client, db_reelle, tmp_path, staging_tmp, qdrant_maj, monkeypatch):
        import app.api.v1.documents as docs_module

        monkeypatch.setattr(docs_module.settings, "documents_storage_path", str(tmp_path))
        doc = _doc_en_base(db_reelle, version=2, content_hash="hash-v2")
        _version_en_base(db_reelle, doc, 1, stored_path="/introuvable/charte.md", content_hash="hash-v1")

        r = client.post(f"{API}/documents/{doc.doc_id}/versions/1/restaurer")

        assert r.status_code == 409
        assert "n'est plus disponible" in r.json()["detail"]

    def test_403_hors_domaine(self, client, db_reelle, backoffice_it, tmp_path, staging_tmp, qdrant_maj):
        doc = _doc_en_base(db_reelle, domaine="RH", version=2)
        _version_en_base(db_reelle, doc, 1, racine=tmp_path)

        assert client.post(f"{API}/documents/{doc.doc_id}/versions/1/restaurer").status_code == 403


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


# ──────────────────────────────────────────────────────────────────────────────
# La chaîne complète : preview → confirm → job
# ──────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def job_maj_reel(monkeypatch, tmp_path, qdrant_maj):
    """Le vrai `document_update_job`, branché sur la base réelle.

    Qdrant, l'embedding et le chunking sont mockés ; Postgres, le disque et la
    détection d'obsolescence sont réels. `qdrant_maj` fournit déjà le mock du
    module — le job et l'aperçu partagent ainsi la même vue de la version
    sortante, comme en production.
    """
    import app.api.v1.documents as docs_module
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

    lance = MagicMock()
    lance.apply_async.return_value = SimpleNamespace(id=str(uuid.uuid4()))
    monkeypatch.setattr(docs_module, "document_update_job", lance)

    def executer():
        """Rejoue le job avec **exactement** les kwargs produits par `confirm`."""
        kwargs = lance.apply_async.call_args.kwargs["kwargs"]
        maj_module.document_update_job(**kwargs)
        return kwargs

    return SimpleNamespace(executer=executer, mock=lance)


@pytest.mark.integration
class TestChaineComplete:
    """API et worker sont testés séparément partout ailleurs — donc jamais l'un
    contre l'autre. Un kwarg renommé d'un côté passerait les deux suites et ne
    casserait qu'en production. Ces tests ferment la couture."""

    def test_maj_de_bout_en_bout(self, client, db_reelle, staging_tmp, job_maj_reel):
        doc = _doc_en_base(db_reelle, version=1, content_hash="hash-v1")
        reponse = _reponse_sur_chunk(db_reelle, doc.doc_id, chunk_index=0)

        apercu = _preview(client, doc.doc_id).json()
        assert apercu["nb_obsoletes"] == 1, "le passage « 2 jours » a disparu en v2"

        r = client.post(
            f"{API}/documents/{doc.doc_id}/versions/confirm",
            json={"staging_id": apercu["staging_id"]},
        )
        assert r.status_code == 200
        db_reelle.refresh(doc)
        assert doc.statut == "EN_MAJ", "le verrou doit tenir entre confirm et la fin du job"

        job_maj_reel.executer()

        db_reelle.expire_all()
        assert doc.version == 2
        assert doc.statut == "ACTIF"
        assert doc.update_job_id is None
        # L'aperçu annonçait 1 réponse obsolète : le job doit en produire exactement 1.
        assert reponse.obsolete is True
        assert reponse.obsolete_raison == "DOC_MIS_A_JOUR"
        assert reponse.obsolete_version == 2
        assert reponse.nb_validations == 3, "les validations acquises sont conservées"

    def test_reformatage_ne_rend_rien_obsolete(self, client, db_reelle, staging_tmp, job_maj_reel):
        """Non-régression décisive : même fond, autre mise en forme → 0 obsolète.

        C'est ce qui distingue « on cherche un passage » de « on compare des
        découpages ». Si ce test tombe, la détection produit des faux positifs en
        masse et le système devient inutilisable.
        """
        doc = _doc_en_base(db_reelle, version=1, content_hash="hash-v1")
        reponse = _reponse_sur_chunk(db_reelle, doc.doc_id, chunk_index=0)
        reformate = _TEXTE_V1.replace(b" ", b"  ").replace(b"\n\n", b"\n\n\n")

        apercu = _preview(client, doc.doc_id, content=reformate).json()
        assert apercu["nb_obsoletes"] == 0

        client.post(
            f"{API}/documents/{doc.doc_id}/versions/confirm",
            json={"staging_id": apercu["staging_id"]},
        )
        job_maj_reel.executer()

        db_reelle.expire_all()
        assert doc.version == 2
        assert reponse.obsolete is False

    def test_restauration_cree_une_nouvelle_version(
        self, client, db_reelle, tmp_path, staging_tmp, job_maj_reel
    ):
        """Restaurer la v1 depuis la v2 crée une **v3**, jamais une v1 rembobinée."""
        from app.models.document_version import DocumentVersion

        doc = _doc_en_base(db_reelle, version=2, content_hash="hash-v2")
        _version_en_base(db_reelle, doc, 1, contenu=_TEXTE_V1, racine=tmp_path, content_hash="hash-v1")
        _version_en_base(db_reelle, doc, 2, contenu=_TEXTE_V2, racine=tmp_path, content_hash="hash-v2")

        apercu = client.post(f"{API}/documents/{doc.doc_id}/versions/1/restaurer").json()
        assert apercu["version_cible"] == 3

        client.post(
            f"{API}/documents/{doc.doc_id}/versions/confirm",
            json={"staging_id": apercu["staging_id"]},
        )
        kwargs = job_maj_reel.executer()
        assert kwargs["restauree_depuis"] == 1

        db_reelle.expire_all()
        assert doc.version == 3
        lignes = {
            v.version: v
            for v in db_reelle.query(DocumentVersion).filter(DocumentVersion.doc_id == doc.doc_id)
        }
        assert set(lignes) == {1, 2, 3}, "aucune version n'est réécrite ni supprimée"
        assert lignes[3].restauree_depuis == 1
        assert lignes[3].remplacee_at is None, "la v3 est la version courante"
        assert lignes[2].remplacee_at is not None, "la v2 est archivée"

    def test_le_verrou_est_libere_si_le_job_echoue(
        self, client, db_reelle, staging_tmp, job_maj_reel, monkeypatch
    ):
        """Sans `on_failure`, un échec laisserait le document en `EN_MAJ` à vie —
        plus aucune mise à jour ni suppression possible, sans voie de sortie."""
        import app.workers.document_update as maj_module

        doc = _doc_en_base(db_reelle, version=1, content_hash="hash-v1")
        apercu = _preview(client, doc.doc_id).json()
        client.post(
            f"{API}/documents/{doc.doc_id}/versions/confirm",
            json={"staging_id": apercu["staging_id"]},
        )
        monkeypatch.setattr(
            maj_module, "embed_texts", MagicMock(side_effect=RuntimeError("Albert indisponible"))
        )

        kwargs = job_maj_reel.mock.apply_async.call_args.kwargs["kwargs"]
        # Hors worker (`called_directly`), `self.retry()` ré-émet l'exception
        # d'origine au lieu de lever `Retry` : on assiste donc au dernier essai.
        # `on_failure` est ce que Celery appellerait ensuite, une fois les
        # tentatives épuisées — c'est lui qui doit rendre la main.
        with pytest.raises(RuntimeError, match="Albert indisponible"):
            maj_module.document_update_job(**kwargs)
        maj_module.document_update_job.on_failure(
            RuntimeError("Albert indisponible"), "task-1", (), kwargs, None
        )

        db_reelle.expire_all()
        assert doc.statut == "ACTIF"
        assert doc.version == 1, "la version ne bascule pas sur un échec"
        assert doc.update_job_id is None
