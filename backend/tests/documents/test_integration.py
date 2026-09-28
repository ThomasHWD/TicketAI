"""Tests d'intégration nécessitant Qdrant réel et la base de test."""

import uuid

import pytest

from .helpers import (
    _TEXTE_V1,
    _TEXTE_V2,
    API,
    _doc_avec_fichier,
    _doc_en_base,
    _preview,
    _reponse_sur_chunk,
    _version_en_base,
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

    restants, _ = real_client.scroll(
        collection_name=COLLECTION_NAME,
        scroll_filter=Filter(must=[FieldCondition(key="doc_id", match=MatchValue(value=qdrant_doc))]),
        limit=10,
    )
    assert restants == []
    assert client.get(f"{API}/documents").json()["total"] == 0
    assert client.get(f"{API}/documents/{qdrant_doc}/chunks").status_code == 404


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
        ing,
        "embed_texts",
        lambda textes, is_query=False: [
            {"dense": [0.1] * 1024, "sparse": {"indices": [0, 1], "values": [0.5, 0.5]}} for _ in textes
        ],
    )

    tmp_file = tmp_path / "upload.md"
    tmp_file.write_text("# Charte\n\nContenu.", encoding="utf-8")
    doc_id = str(uuid.uuid4())

    try:
        result = ing.ingestion_job.apply(
            kwargs={
                "file_path": str(tmp_file),
                "filename": "charte.md",
                "domaine": "RH",
                "description": "Charte 2025",
                "content_hash": "b" * 64,
                "uploaded_by": None,
                "doc_id": doc_id,
            }
        ).get()

        assert result["statut"] == "OK"
        assert result["doc_id"] == doc_id
        assert result["nb_chunks"] == 2

        attendu = tmp_path / "storage" / doc_id / "v1" / "charte.md"
        assert attendu.is_file()
        assert not tmp_file.exists()

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


@pytest.mark.integration
class TestChaineComplete:
    """API et worker sont testés séparément partout ailleurs — donc jamais l'un
    contre l'autre. Un kwarg renommé d'un côté passerait les deux suites et ne
    casserait qu'en production. Ces tests ferment la couture."""

    def test_maj_de_bout_en_bout(self, client, db_reelle, staging_tmp, job_maj_reel):
        doc = _doc_avec_fichier(db_reelle, staging_tmp, version=1)
        reponse = _reponse_sur_chunk(db_reelle, doc.doc_id, chunk_index=0, domaine="RH")

        apercu = _preview(client, doc.doc_id).json()
        assert apercu["nb_prioritaires"] == 1, "le passage « 2 jours » a été réécrit en v2"
        assert apercu["nb_a_analyser"] == 1

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

        assert reponse.obsolete is False
        assert reponse.a_relire is True
        assert reponse.a_relire_raison == "ANALYSE_EN_COURS"
        assert reponse.a_relire_doc_id == doc.doc_id
        assert reponse.nb_validations == 3, "les validations acquises sont conservées"

        [enfilee] = job_maj_reel.enfilees
        assert enfilee["queue"] == "queue_questions"
        assert enfilee["kwargs"] == {
            "doc_id": doc.doc_id,
            "version": 2,
            "domaine": "RH",
            "indices_disparus": [0],
            "version_sortante": 1,
        }

    def test_reformatage_ne_rend_rien_obsolete(self, client, db_reelle, staging_tmp, job_maj_reel):
        """Non-régression décisive : même fond, autre mise en forme → rien du tout.

        C'est ce qui distingue « on cherche un passage » de « on compare des
        découpages ». Si ce test tombe, la détection produit des faux positifs en
        masse et le système devient inutilisable — et, depuis que le verdict est
        rendu par le LLM, elle facture en plus un appel par réponse du domaine.
        """
        doc = _doc_avec_fichier(db_reelle, staging_tmp, version=1)
        reponse = _reponse_sur_chunk(db_reelle, doc.doc_id, chunk_index=0, domaine="RH")
        reformate = _TEXTE_V1.replace(b" ", b"  ").replace(b"\n\n", b"\n\n\n")

        apercu = _preview(client, doc.doc_id, content=reformate).json()
        assert apercu["nb_prioritaires"] == 0
        assert apercu["nb_unites"] == 0
        assert apercu["nb_a_analyser"] == 0

        client.post(
            f"{API}/documents/{doc.doc_id}/versions/confirm",
            json={"staging_id": apercu["staging_id"]},
        )
        job_maj_reel.executer()

        db_reelle.expire_all()
        assert doc.version == 2
        assert reponse.obsolete is False
        assert reponse.a_relire is False, "un reformatage ne doit pas créer de tâche"
        assert job_maj_reel.enfilees == [], "ni facturer un seul appel Albert"

    def test_restauration_cree_une_nouvelle_version(self, client, db_reelle, tmp_path, staging_tmp, job_maj_reel):
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
        lignes = {v.version: v for v in db_reelle.query(DocumentVersion).filter(DocumentVersion.doc_id == doc.doc_id)}
        assert set(lignes) == {1, 2, 3}, "aucune version n'est réécrite ni supprimée"
        assert lignes[3].restauree_depuis == 1
        assert lignes[3].remplacee_at is None, "la v3 est la version courante"
        assert lignes[2].remplacee_at is not None, "la v2 est archivée"

    def test_le_verrou_est_libere_si_le_job_echoue(self, client, db_reelle, staging_tmp, job_maj_reel, monkeypatch):
        """Sans `on_failure`, un échec laisserait le document en `EN_MAJ` à vie —
        plus aucune mise à jour ni suppression possible, sans voie de sortie."""
        from unittest.mock import MagicMock

        import app.workers.document_update as maj_module

        doc = _doc_en_base(db_reelle, version=1, content_hash="hash-v1")
        apercu = _preview(client, doc.doc_id).json()
        client.post(
            f"{API}/documents/{doc.doc_id}/versions/confirm",
            json={"staging_id": apercu["staging_id"]},
        )
        monkeypatch.setattr(maj_module, "embed_texts", MagicMock(side_effect=RuntimeError("Albert indisponible")))

        kwargs = job_maj_reel.mock.apply_async.call_args.kwargs["kwargs"]
        with pytest.raises(RuntimeError, match="Albert indisponible"):
            maj_module.document_update_job(**kwargs)
        maj_module.document_update_job.on_failure(RuntimeError("Albert indisponible"), "task-1", (), kwargs, None)

        db_reelle.expire_all()
        assert doc.statut == "ACTIF"
        assert doc.version == 1, "la version ne bascule pas sur un échec"
        assert doc.update_job_id is None
