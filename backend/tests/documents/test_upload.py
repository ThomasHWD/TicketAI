"""Tests pour POST /documents — validation, dédoublonnage, homonymes."""

import pytest

from .helpers import (
    _MD_CONTENT,
    _PDF_MAGIC,
    _doc_en_base,
    _job_kwargs,
    _upload,
)


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
            "file_path",
            "filename",
            "domaine",
            "description",
            "content_hash",
            "uploaded_by",
            "doc_id",
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
        doc = _doc_en_base(db_reelle, domaine="IT", filename="deja.md", content_hash=self._hash(), version=2)

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

        r = _upload(client, domaine="IT", filename="charte.md", content=b"# Contenu different", force_nouveau=True)

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

        _doc_en_base(
            db_reelle, domaine="IT", filename="charte.md", content_hash=hashlib.sha256(_MD_CONTENT).hexdigest()
        )

        r = _upload(client, domaine="IT", filename="charte.md")

        assert r.status_code == 200
        assert r.json()["statut"] == "DÉJÀ_INDEXÉ"
