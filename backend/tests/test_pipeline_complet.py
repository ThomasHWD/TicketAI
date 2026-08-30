"""Tests du pipeline complet de mise à jour de document.

Complète les quatre fichiers existants sur deux cas non encore couverts :

1. **Reformatage pur + réponse EN_ATTENTE** : la réponse ne doit PAS être périmée
   (condition `a_du_neuf = bool(changements["nb_unites"])` en l.341 du worker).
   `test_reformatage_ne_declenche_rien` (test_document_update.py) vérifie une
   VALIDÉE — ce fichier complète avec une EN_ATTENTE.

2. **Chaîne complète** : `document_update_job` → `reverification_job` enchaînés
   sur Postgres réel, sans passer par le broker. Les deux workers sont testés en
   isolation dans leurs fichiers respectifs ; le test ici vérifie que leur
   assemblage produit le bon état final.

Albert, Qdrant et le broker sont bouchonnés dans les deux cas.
"""

import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from app.models.document import Document
from app.models.document_version import DocumentVersion
from app.models.reponse import Reponse
from app.models.reponse_chunk import ReponseChunk
from app.models.ticket import Ticket

DOMAINE = "RH"
TEXTE_V1 = (
    "Le télétravail est limité à 2 jours par semaine, sur accord du manager.\n\n"
    "La demande se fait via le portail RH, au moins 5 jours ouvrés à l'avance."
)
TEXTE_V2 = TEXTE_V1.replace("2 jours", "3 jours")


def _point(index: int, contenu: str):
    return SimpleNamespace(payload={"chunk_index": index, "contenu": contenu})


@pytest.fixture
def env(tmp_path, monkeypatch, db_session):
    """Document v1 + réponses en base, Qdrant + Albert + broker bouchonnés.

    Reproduit le pattern de `scenario_maj` (test_document_update.py) et `lot`
    (test_reverification_worker.py) dans une seule fixture pour permettre de
    tester les deux workers enchaînés sans infrastructure Celery/Valkey.
    """
    import app.services.obsolescence as obso
    import app.services.reverification_candidates as candidates
    import app.workers.document_update as maj
    import app.workers.reverification as worker
    from app.config import settings

    monkeypatch.setattr(settings, "documents_storage_path", str(tmp_path / "storage"))
    monkeypatch.setattr(maj, "broadcast_sync", lambda *a, **k: None)
    monkeypatch.setattr(worker, "broadcast_sync", lambda *a, **k: None)
    monkeypatch.setattr(obso, "delete_response_point", lambda _id: None)
    # Seules les citantes ; les voisines sont hors périmètre de ces tests.
    monkeypatch.setattr(candidates, "_voisines", lambda db, domaine, unites: [])
    # Évite toute connexion au broker Celery/Valkey quand une EN_ATTENTE est périmée.
    monkeypatch.setattr(maj, "requeuer_en_attente", lambda db, reponses: None)

    qdrant_mock = MagicMock()
    qdrant_mock.scroll.return_value = ([], None)
    monkeypatch.setattr(maj, "client", qdrant_mock)

    monkeypatch.setattr(maj, "chunk_text", lambda pages: "\n\n".join(pages).split("\n\n"))
    monkeypatch.setattr(
        maj,
        "embed_texts",
        lambda chunks, is_query=False: [
            {"dense": [0.1] * 1024, "sparse": {"indices": [1], "values": [0.5]}} for _ in chunks
        ],
    )

    doc_id = str(uuid.uuid4())

    # Fichier V1 sur disque — document_update_job le relit pour calculer le diff.
    dossier_v1 = tmp_path / "storage" / doc_id / "v1"
    dossier_v1.mkdir(parents=True)
    fichier_v1 = dossier_v1 / "charte.md"
    fichier_v1.write_text(TEXTE_V1, encoding="utf-8")

    db_session.add(
        Document(
            doc_id=doc_id,
            filename="charte.md",
            domaine=DOMAINE,
            version=1,
            nb_chunks=2,
            stored_path=str(fichier_v1),
            statut="ACTIF",
        )
    )
    db_session.add(
        DocumentVersion(
            doc_id=doc_id,
            version=1,
            filename="charte.md",
            nb_chunks=2,
            stored_path=str(fichier_v1),
        )
    )
    db_session.commit()

    # Qdrant retourne les chunks de V1 (capturés par le job avant suppression).
    qdrant_mock.scroll.return_value = (
        [_point(i, t) for i, t in enumerate(TEXTE_V1.split("\n\n"))],
        None,
    )

    # Les kwargs de reverification_job enfilés par document_update_job.
    enfilees: list[dict] = []
    monkeypatch.setattr(
        worker.reverification_job,
        "apply_async",
        lambda **kw: enfilees.append(kw),
    )

    def _reponse(
        *,
        cite: bool = True,
        statut: str = "VALIDÉE",
        canonique: bool = True,
        nb_validations: int = 3,
    ) -> Reponse:
        ticket = Ticket(
            question="Combien de jours de télétravail ?",
            domaine=DOMAINE,
            statut_job="TERMINÉ",
        )
        db_session.add(ticket)
        db_session.flush()
        r = Reponse(
            ticket_id=ticket.id,
            contenu="Le maximum est 2 jours par semaine.",
            source="LLM",
            statut=statut,
            canonique=canonique,
            nb_validations=nb_validations,
        )
        db_session.add(r)
        db_session.flush()
        if cite:
            db_session.add(ReponseChunk(reponse_id=r.id, doc_id=doc_id, chunk_index=0))
        db_session.commit()
        return r

    def _job_kwargs(texte: str = TEXTE_V2) -> dict:
        fichier = tmp_path / "nouveau.md"
        fichier.write_text(texte, encoding="utf-8")
        return {
            "doc_id": doc_id,
            "new_version": 2,
            "file_path": str(fichier),
            "filename": "charte.md",
            "description": "Charte télétravail v2",
            "content_hash": "hash-v2",
            "uploaded_by": None,
        }

    return SimpleNamespace(
        doc_id=doc_id,
        db=db_session,
        qdrant=qdrant_mock,
        enfilees=enfilees,
        reponse=_reponse,
        job_kwargs=_job_kwargs,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 1. Reformatage pur + réponse EN_ATTENTE
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.integration
class TestEnAttenteReformatage:
    """Reformatage pur (0 unité) : les réponses EN_ATTENTE ne sont pas périmées.

    La condition `a_du_neuf = bool(changements["nb_unites"])` dans
    `document_update_job` est le seul verrou. `test_reformatage_ne_declenche_rien`
    (test_document_update.py) couvre une VALIDÉE ; ce test complète avec une
    EN_ATTENTE, dont le cycle de vie est différent (périmée, pas a_relire).
    """

    def test_en_attente_citante_non_perimee_si_zero_unite(self, env):
        """Même texte → 0 unité → a_du_neuf=False → perimer_en_attente non appelée."""
        from app.workers.document_update import document_update_job

        r = env.reponse(cite=True, statut="EN_ATTENTE", canonique=False, nb_validations=0)

        # Le nouveau fichier est identique à V1 : 0 unité de changement.
        resultat = document_update_job(**env.job_kwargs(texte=TEXTE_V1))

        env.db.refresh(r)
        assert r.statut == "EN_ATTENTE"
        assert r.obsolete is False
        assert resultat["nb_a_analyser"] == 0
        assert env.enfilees == []

    def test_en_attente_citante_perimee_si_changement(self, env):
        """Contrôle négatif : avec ≥1 unité, la EN_ATTENTE est bien périmée.

        Vérifie que la condition `a_du_neuf` fonctionne dans les deux sens et
        que le mock de `requeuer_en_attente` ne masque pas une absence de périmètre.
        """
        from app.workers.document_update import document_update_job

        r = env.reponse(cite=True, statut="EN_ATTENTE", canonique=False, nb_validations=0)

        # Texte modifié → ≥1 unité → EN_ATTENTE doit être périmée.
        document_update_job(**env.job_kwargs(texte=TEXTE_V2))

        env.db.refresh(r)
        assert r.obsolete is True
        assert r.obsolete_raison == "DOC_MIS_A_JOUR"


# ─────────────────────────────────────────────────────────────────────────────
# 2. Chaîne complète : document_update_job → reverification_job
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.integration
class TestBoutEnBoutComplet:
    """document_update_job → reverification_job enchaînés sans broker.

    Les deux workers sont testés en isolation dans leurs fichiers respectifs :
    `test_document_update.py` vérifie que document_update_job laisse les bonnes
    réponses en ANALYSE_EN_COURS, et `test_reverification_worker.py` part de cet
    état déjà constitué. Ce test vérifie que la soudure est correcte : l'état laissé
    par le premier est bien celui qu'attend le second.
    """

    @staticmethod
    def _patcher_albert(monkeypatch, verdict: str) -> None:
        import app.services.reverification_scoring as scoring

        monkeypatch.setattr(
            scoring,
            "rerank",
            lambda q, docs, top_k: [{**docs[0], "rerank_score": 0.9}],
        )
        monkeypatch.setattr(
            scoring,
            "chat",
            lambda messages, **k: '{"verdict": "%s", "justification": "Test."}' % verdict,
        )

    def test_contredite_bout_en_bout(self, env, monkeypatch):
        """v1 → v2 (1 chiffre change) : la citante est retirée après jugement CONTREDITE."""
        from app.workers.document_update import document_update_job
        from app.workers.reverification import restees_en_analyse, reverification_job

        r = env.reponse(cite=True, statut="VALIDÉE", canonique=True, nb_validations=3)
        self._patcher_albert(monkeypatch, "CONTREDITE")

        # Phase 1 — mise à jour du document.
        document_update_job(**env.job_kwargs(texte=TEXTE_V2))

        env.db.refresh(r)
        assert r.a_relire is True
        assert r.a_relire_raison == "ANALYSE_EN_COURS"
        assert len(env.enfilees) == 1

        # Phase 2 — révérification enchaînée directement sans passer par le broker.
        bilan = reverification_job(**env.enfilees[0]["kwargs"])

        env.db.expire_all()
        assert bilan["statut"] == "OK"
        assert r.obsolete is True
        assert r.obsolete_raison == "CONTREDITE_PAR_MAJ"
        assert r.a_relire is False
        assert restees_en_analyse(env.db, env.doc_id, 2) == []

    def test_intacte_bout_en_bout(self, env, monkeypatch):
        """v1 → v2 (1 chiffre change) : la citante est blanchie après jugement INTACTE."""
        from app.workers.document_update import document_update_job
        from app.workers.reverification import restees_en_analyse, reverification_job

        r = env.reponse(cite=True, statut="VALIDÉE", canonique=True, nb_validations=3)
        self._patcher_albert(monkeypatch, "INTACTE")

        document_update_job(**env.job_kwargs(texte=TEXTE_V2))

        env.db.refresh(r)
        # L'état intermédiaire : le document_update_job a bien marqué ANALYSE_EN_COURS.
        assert r.a_relire is True
        assert r.a_relire_raison == "ANALYSE_EN_COURS"

        bilan = reverification_job(**env.enfilees[0]["kwargs"])

        env.db.expire_all()
        assert bilan["statut"] == "OK"
        assert r.obsolete is False
        assert r.a_relire is False
        assert restees_en_analyse(env.db, env.doc_id, 2) == []

    def test_aucune_analyse_en_cours_residuelle_apres_incertain(self, env, monkeypatch):
        """INCERTAIN : la réponse part en relecture mais ANALYSE_EN_COURS est résolu.

        La propriété centrale du dispositif (documentée dans test_reverification_worker.py) :
        ANALYSE_EN_COURS est le seul état transitoire, et le job est obligé de le
        résoudre pour chaque réponse qu'il a reçue.
        """
        from app.workers.document_update import document_update_job
        from app.workers.reverification import restees_en_analyse, reverification_job

        r = env.reponse(cite=True, statut="VALIDÉE", canonique=True, nb_validations=3)
        self._patcher_albert(monkeypatch, "INCERTAIN")

        document_update_job(**env.job_kwargs(texte=TEXTE_V2))
        reverification_job(**env.enfilees[0]["kwargs"])

        env.db.expire_all()
        assert r.obsolete is False
        assert r.a_relire is True
        assert r.a_relire_raison == "DOC_MODIFIÉ"
        # Transitoire résolu : ANALYSE_EN_COURS disparu, même pour un INCERTAIN.
        assert restees_en_analyse(env.db, env.doc_id, 2) == []
