"""Tests du backfill de la table `documents` depuis Qdrant.

Qdrant est mocké (on injecte les points), Postgres est réel : c'est l'écriture des
lignes qui est vérifiée, pas le scroll.
"""

import uuid
from unittest.mock import MagicMock

import pytest

pytestmark = pytest.mark.integration


def _point(**payload):
    p = MagicMock()
    p.payload = payload
    return p


@pytest.fixture
def qdrant_points(monkeypatch):
    """Injecte une liste de points comme unique page de scroll."""
    import app.services.document_backfill as backfill

    mock_client = MagicMock()

    def _set(points):
        mock_client.scroll.return_value = (points, None)

    mock_client.scroll.return_value = ([], None)
    monkeypatch.setattr(backfill, "client", mock_client)
    return _set


def _reconcilier(db):
    from app.services.document_backfill import reconcilier_documents

    return reconcilier_documents(db)


def _documents(db):
    from app.models.document import Document

    return db.query(Document).all()


class TestBackfill:
    def test_cree_le_document_et_la_ligne_v1(self, db_session, qdrant_points):
        from app.models.document_version import DocumentVersion

        doc_id = str(uuid.uuid4())
        qdrant_points(
            [
                _point(doc_id=doc_id, chunk_index=0, source="charte.md", domaine="RH", contenu="a"),
                _point(doc_id=doc_id, chunk_index=1, source="charte.md", domaine="RH", contenu="b"),
            ]
        )

        stats = _reconcilier(db_session)

        assert stats["documents_crees"] == 1
        doc = _documents(db_session)[0]
        assert (doc.doc_id, doc.filename, doc.domaine) == (doc_id, "charte.md", "RH")
        assert doc.version == 1
        assert doc.nb_chunks == 2
        assert doc.statut == "ACTIF"

        version = db_session.query(DocumentVersion).filter(DocumentVersion.doc_id == doc_id).one()
        assert version.version == 1
        assert version.nb_chunks == 2

    def test_ignore_les_points_de_feedback(self, db_session, qdrant_points):
        """Les points de feedback_job indexent une question et n'ont pas de doc_id :
        les compter créerait un document fantôme portant le texte d'une réponse."""
        qdrant_points(
            [
                _point(
                    reponse_id=str(uuid.uuid4()),
                    ticket_id=str(uuid.uuid4()),
                    contenu="Puis-je télétravailler ?",
                    domaine="RH",
                ),
            ]
        )

        stats = _reconcilier(db_session)

        assert stats["documents_qdrant"] == 0
        assert _documents(db_session) == []

    def test_sans_auteur_connu_uploaded_by_null(self, db_session, qdrant_points):
        """Cas nominal des documents antérieurs au champ : l'absence d'auteur ne doit
        pas faire échouer le backfill."""
        doc_id = str(uuid.uuid4())
        qdrant_points([_point(doc_id=doc_id, chunk_index=0, source="vieux.md", domaine="IT")])

        _reconcilier(db_session)

        assert _documents(db_session)[0].uploaded_by is None

    def test_auteur_repris_de_document_uploads(self, db_session, qdrant_points, user_factory):
        from app.models.document_upload import DocumentUpload

        user = user_factory("ADMIN")
        doc_id = str(uuid.uuid4())
        db_session.add(DocumentUpload(doc_id=doc_id, user_id=user.id, domaine="IT", filename="vieux.md"))
        db_session.commit()

        qdrant_points([_point(doc_id=doc_id, chunk_index=0, source="vieux.md", domaine="IT")])
        _reconcilier(db_session)

        assert _documents(db_session)[0].uploaded_by == user.id

    def test_idempotent(self, db_session, qdrant_points):
        from app.models.document_version import DocumentVersion

        doc_id = str(uuid.uuid4())
        qdrant_points([_point(doc_id=doc_id, chunk_index=0, source="charte.md", domaine="RH")])

        _reconcilier(db_session)
        stats = _reconcilier(db_session)

        assert stats["documents_crees"] == 0
        assert stats["documents_existants"] == 1
        assert len(_documents(db_session)) == 1
        assert db_session.query(DocumentVersion).count() == 1

    def test_document_absent_de_qdrant_non_recree(self, db_session, qdrant_points):
        """Une ingestion échouée laisse une ligne document_uploads sans point Qdrant :
        Qdrant fait foi, ce doc_id ne doit pas devenir un document actif."""
        from app.models.document_upload import DocumentUpload

        db_session.add(
            DocumentUpload(doc_id=str(uuid.uuid4()), user_id=None, domaine="IT", filename="jamais_indexe.md")
        )
        db_session.commit()
        qdrant_points([])

        _reconcilier(db_session)

        assert _documents(db_session) == []
