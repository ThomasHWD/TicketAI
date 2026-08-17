"""Tests unitaires pour les helpers d'ingestion (sanitize_filename, extract_text, store_file, point_id)."""

import os
import uuid
from pathlib import Path
from unittest.mock import MagicMock

import pytest


class TestSanitizeFilename:
    def test_normal(self):
        from app.services.document_service import sanitize_filename

        assert sanitize_filename("rapport_2025.pdf") == "rapport_2025.pdf"

    def test_path_traversal(self):
        from app.services.document_service import sanitize_filename

        assert sanitize_filename("../../etc/passwd") == "passwd"

    def test_null_bytes(self):
        from app.services.document_service import sanitize_filename

        assert "\x00" not in sanitize_filename("fichier\x00.pdf")

    def test_special_chars_replaced(self):
        from app.services.document_service import sanitize_filename

        # Pas de "/" dans le nom pour éviter que basename le tronque
        result = sanitize_filename("doc (1); injection$.pdf")
        assert ";" not in result
        assert "$" not in result

    def test_empty_raises(self):
        from app.services.document_service import sanitize_filename
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc:
            sanitize_filename("")
        assert exc.value.status_code == 400

    def test_dot_only_raises(self):
        from app.services.document_service import sanitize_filename
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

        fixture = Path(__file__).parent.parent / "Accord_Teletravail_Reglementation.md"
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
