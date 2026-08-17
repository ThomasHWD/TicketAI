"""Tests pour GET /documents, /chunks, /download et DELETE /documents."""

import uuid

import pytest

from .helpers import _doc_en_base, _make_point


@pytest.mark.integration
class TestListDocuments:
    def test_liste_vide(self, client, db_reelle):
        r = client.get("/api/v1/documents")
        assert r.status_code == 200
        assert r.json() == {"total": 0, "items": []}

    def test_champs_du_document(self, client, db_reelle):
        doc = _doc_en_base(db_reelle, filename="charte.md", description="Charte 2025", nb_chunks=7)

        item = client.get("/api/v1/documents").json()["items"][0]

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

        assert client.get("/api/v1/documents").json()["items"][0]["nb_versions"] == 3

    def test_plusieurs_docs(self, client, db_reelle):
        d1 = _doc_en_base(db_reelle, domaine="IT", nb_chunks=2)
        d2 = _doc_en_base(db_reelle, domaine="RH", nb_chunks=1)

        body = client.get("/api/v1/documents").json()

        assert body["total"] == 2
        assert {i["doc_id"]: i["nb_chunks"] for i in body["items"]} == {d1.doc_id: 2, d2.doc_id: 1}

    def test_document_supprime_absent_de_la_liste(self, client, db_reelle):
        _doc_en_base(db_reelle, statut="SUPPRIMÉ")

        assert client.get("/api/v1/documents").json()["items"] == []

    def test_filtre_domaine(self, client, db_reelle):
        _doc_en_base(db_reelle, domaine="IT")
        attendu = _doc_en_base(db_reelle, domaine="RH")

        body = client.get("/api/v1/documents?domaine=RH").json()

        assert [i["doc_id"] for i in body["items"]] == [attendu.doc_id]

    def test_filtre_domaine_inconnu_retourne_liste_vide(self, client, db_reelle):
        _doc_en_base(db_reelle, domaine="IT")

        assert client.get("/api/v1/documents?domaine=INCONNU").json()["items"] == []

    def test_filtre_domaines_multiples(self, client, db_reelle):
        _doc_en_base(db_reelle, domaine="IT")
        _doc_en_base(db_reelle, domaine="RH")
        _doc_en_base(db_reelle, domaine="LEGAL")

        body = client.get("/api/v1/documents?domaines=IT,RH").json()

        assert body["total"] == 2

    def test_ne_scrolle_plus_qdrant(self, client, db_reelle, mock_qdrant):
        """Le listing scrollait la collection entière ; il lit maintenant une table."""
        _doc_en_base(db_reelle)

        client.get("/api/v1/documents")

        mock_qdrant.scroll.assert_not_called()


@pytest.mark.integration
class TestGetChunks:
    def test_chunks_tries_par_index(self, client, db_reelle, mock_qdrant):
        doc = _doc_en_base(db_reelle)
        mock_qdrant.scroll.return_value = ([_make_point(doc.doc_id, i) for i in [2, 0, 1]], None)

        body = client.get(f"/api/v1/documents/{doc.doc_id}/chunks").json()

        assert [c["chunk_index"] for c in body["chunks"]] == [0, 1, 2]
        assert "contenu" in body["chunks"][0]

    def test_doc_inexistant_renvoie_404(self, client, db_reelle, mock_qdrant):
        r = client.get(f"/api/v1/documents/{uuid.uuid4()}/chunks")
        assert r.status_code == 404

    def test_doc_supprime_renvoie_404(self, client, db_reelle, mock_qdrant):
        doc = _doc_en_base(db_reelle, statut="SUPPRIMÉ")
        r = client.get(f"/api/v1/documents/{doc.doc_id}/chunks")
        assert r.status_code == 404

    def test_hors_domaine_renvoie_403(self, client, db_reelle, mock_qdrant, backoffice_it):
        doc = _doc_en_base(db_reelle, domaine="RH")
        r = client.get(f"/api/v1/documents/{doc.doc_id}/chunks")
        assert r.status_code == 403


@pytest.mark.integration
class TestDownloadDocument:
    def test_doc_inexistant_renvoie_404(self, client, db_reelle):
        r = client.get(f"/api/v1/documents/{uuid.uuid4()}/download")
        assert r.status_code == 404

    def test_fichier_absent_sur_disque(self, client, db_reelle):
        doc = _doc_en_base(db_reelle, stored_path="/tmp/inexistant/doc.md")
        r = client.get(f"/api/v1/documents/{doc.doc_id}/download")
        assert r.status_code == 404
        assert "disque" in r.json()["detail"]

    def test_renvoie_le_fichier(self, client, db_reelle, tmp_path):
        contenu = b"# Contenu du document de test"
        f = tmp_path / "doc.md"
        f.write_bytes(contenu)
        doc = _doc_en_base(db_reelle, filename="doc.md", stored_path=str(f))

        r = client.get(f"/api/v1/documents/{doc.doc_id}/download")

        assert r.status_code == 200
        assert r.content == contenu
        assert "attachment" in r.headers.get("content-disposition", "")

    def test_repli_sur_l_ancien_emplacement(self, client, db_reelle, tmp_path, monkeypatch):
        """Documents backfillés : leur fichier est resté à la racine de {doc_id}/."""
        import app.api.v1.documents.core as docs_module

        monkeypatch.setattr(docs_module.settings, "documents_storage_path", str(tmp_path))
        doc = _doc_en_base(db_reelle, filename="doc.md", stored_path=None)
        (tmp_path / doc.doc_id).mkdir()
        (tmp_path / doc.doc_id / "doc.md").write_bytes(b"ancien")

        r = client.get(f"/api/v1/documents/{doc.doc_id}/download")

        assert r.status_code == 200
        assert r.content == b"ancien"

    def test_hors_domaine_renvoie_403(self, client, db_reelle, tmp_path, backoffice_it):
        f = tmp_path / "doc.md"
        f.write_bytes(b"secret RH")
        doc = _doc_en_base(db_reelle, domaine="RH", stored_path=str(f))

        r = client.get(f"/api/v1/documents/{doc.doc_id}/download")

        assert r.status_code == 403


@pytest.mark.integration
class TestDeleteDocument:
    def test_doc_inexistant_renvoie_404(self, client, db_reelle, mock_qdrant):
        r = client.delete(f"/api/v1/documents/{uuid.uuid4()}")
        assert r.status_code == 404

    def test_supprime_les_points_et_marque_la_ligne(self, client, db_reelle, mock_qdrant):
        doc = _doc_en_base(db_reelle)

        r = client.delete(f"/api/v1/documents/{doc.doc_id}")

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
        client.delete(f"/api/v1/documents/{doc.doc_id}")

        conserve = db_reelle.query(Document).filter(Document.doc_id == doc.doc_id).one()
        assert conserve.filename == "charte.md"

    def test_hors_domaine_renvoie_403(self, client, db_reelle, backoffice_it, mock_qdrant):
        doc = _doc_en_base(db_reelle, domaine="RH")

        r = client.delete(f"/api/v1/documents/{doc.doc_id}")

        assert r.status_code == 403
        mock_qdrant.delete.assert_not_called()

    def test_admin_hors_domaine_renvoie_403(self, client, db_reelle, admin_sans_groupe, mock_qdrant):
        """Le rôle ne donne rien ici : supprimer un document, c'est agir sur un
        domaine, et `check_domain_write` n'exempte pas l'administrateur."""
        doc = _doc_en_base(db_reelle, domaine="RH")

        r = client.delete(f"/api/v1/documents/{doc.doc_id}")

        assert r.status_code == 403
        mock_qdrant.delete.assert_not_called()

    def test_par_le_domaine_ok_sans_etre_admin(self, client, db_reelle, backoffice_it, mock_qdrant):
        """Le pendant : celui qui peut remplacer le fichier peut aussi le supprimer."""
        doc = _doc_en_base(db_reelle, domaine="IT")

        r = client.delete(f"/api/v1/documents/{doc.doc_id}")

        assert r.status_code == 200

    def test_maj_en_cours_renvoie_409(self, client, db_reelle, mock_qdrant):
        doc = _doc_en_base(db_reelle, statut="EN_MAJ")

        r = client.delete(f"/api/v1/documents/{doc.doc_id}")

        assert r.status_code == 409
        mock_qdrant.delete.assert_not_called()

    def test_supprime_le_dossier_archives_comprises(self, client, db_reelle, mock_qdrant, tmp_path, monkeypatch):
        """Les fichiers étant rangés par version, effacer le seul dossier de la version
        courante laisserait les archives derrière."""
        import app.api.v1.documents.core as docs_module

        monkeypatch.setattr(docs_module.settings, "documents_storage_path", str(tmp_path))
        doc = _doc_en_base(db_reelle)
        for v in ("v1", "v2"):
            (tmp_path / doc.doc_id / v).mkdir(parents=True)
            (tmp_path / doc.doc_id / v / "doc.md").write_text(v)
        db_reelle.commit()

        client.delete(f"/api/v1/documents/{doc.doc_id}")

        assert not (tmp_path / doc.doc_id).exists()

    def test_sans_fichier_disque_ne_plante_pas(self, client, db_reelle, mock_qdrant, tmp_path, monkeypatch):
        import app.api.v1.documents.core as docs_module

        monkeypatch.setattr(docs_module.settings, "documents_storage_path", str(tmp_path))
        doc = _doc_en_base(db_reelle)

        assert client.delete(f"/api/v1/documents/{doc.doc_id}").status_code == 200

    def test_deux_fois_renvoie_404(self, client, db_reelle, mock_qdrant):
        doc = _doc_en_base(db_reelle)
        client.delete(f"/api/v1/documents/{doc.doc_id}")

        assert client.delete(f"/api/v1/documents/{doc.doc_id}").status_code == 404

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

        r = client.delete(f"/api/v1/documents/{doc.doc_id}")

        assert r.json()["nb_obsoletes"] == 1
        db_reelle.refresh(reponse)
        assert reponse.obsolete is True
        assert reponse.obsolete_raison == "DOC_SUPPRIMÉ"
        assert reponse.obsolete_doc_id == doc.doc_id
        assert reponse.obsolete_version == 3
