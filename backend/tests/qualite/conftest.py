"""Fixtures pour la suite qualité RAG.

Ce conftest shadow le conftest parent sur deux points :
1. `mock_side_effects` (autouse) laisse Qdrant réel et neutralise seulement Celery async + SSE.
2. `db` est une session légère sans DELETE * FROM tables, pour ne pas effacer le seed.

Conventions :
- `faq_seed` (module-scoped) : 3 réponses canoniques DFE, 3 appels embed Albert au setup.
- `docs_ingeres` (module-scoped) : 2 documents .md ingérés (~12 appels embed Albert au setup).
- Les tests DOIVENT utiliser `db` et non `db_session` : `db_session` du parent efface les tables
  reponses/tickets, ce qui détruirait le seed en milieu de module.
"""

import shutil
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from app.config import settings
from app.database import SessionLocal
from app.models.reponse import Reponse
from app.models.ticket import Ticket
from app.services.qdrant import COLLECTION_NAME
from app.services.qdrant import client as qdrant_client
from sqlalchemy import text

FIXTURES_DIR = Path(__file__).parent / "fixtures"
DOMAINE = "Finances et évaluation"

# ── 1. Override mock_side_effects ─────────────────────────────────────────────
# Même nom + autouse=True → shadow le parent pour tous les tests de ce répertoire.
# Laisse Qdrant réel ; neutralise Celery async et les broadcasts SSE.


@pytest.fixture(autouse=True)
def mock_side_effects(monkeypatch):
    import app.api.v1.reponses.actions as actions_module
    import app.main as main_module
    import app.services.broadcast as broadcast_module
    import app.services.question_pipeline as pipeline_module

    monkeypatch.setattr(actions_module.feedback_job, "apply_async", MagicMock())
    monkeypatch.setattr(main_module, "init_collection", MagicMock())
    # broadcast_sync importé niveau module dans question_pipeline
    monkeypatch.setattr(pipeline_module, "broadcast_sync", lambda *a, **k: None)
    # broadcast_sync importé tardivement (lazy) dans question.py ligne ~337
    monkeypatch.setattr(broadcast_module, "broadcast_sync", lambda *a, **k: None)


# ── 2. Collection Qdrant (session, autouse) ───────────────────────────────────


@pytest.fixture(scope="session", autouse=True)
def qdrant_init():
    from app.services.qdrant import init_collection

    assert "test" in COLLECTION_NAME.lower(), (
        f"Sécurité : la collection ciblée « {COLLECTION_NAME} » "
        "ne contient pas 'test' — refus d'initialiser."
    )
    try:
        init_collection()
    except Exception as exc:
        pytest.skip(f"Qdrant injoignable — tests qualité ignorés : {exc!r}")
    yield


# ── 3. Session DB légère (per-test, sans DELETE *) ────────────────────────────


@pytest.fixture
def db(db_schema):
    """Session légère : rollback seul, pas de nettoyage agressif des tables.

    Le seed module-scoped (faq_seed, docs_ingeres) doit survivre entre tests.
    Ne jamais remplacer par db_session ici : db_session efface reponses + tickets.
    """
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


# ── 4. Helper question_job ────────────────────────────────────────────────────


def run_question(
    question: str, domaine: str, monkeypatch, *, mock_tag: bool = True, mock_generate: bool = False
) -> dict:
    """Lance question_job.run() de façon synchrone avec request.id simulé.

    Celery task `bind=True` accède à self.request.id (ligne 83 de question.py) :
    push_request/pop_request injectent un contexte factice sans passer par le broker.
    """
    import app.workers.question as qm
    from app.workers.question import question_job

    if mock_tag:
        monkeypatch.setattr(qm, "suggerer_tag", lambda *a, **k: "test-tag")
    if mock_generate:
        monkeypatch.setattr(qm, "generate", lambda *a, **k: ("Réponse RAG de test.", False))

    question_job.push_request(id=str(uuid.uuid4()), retries=0)
    try:
        return question_job.run(question=question, domaine=domaine)
    finally:
        question_job.pop_request()


# ── 5. Seed réponses canoniques (module-scoped) ───────────────────────────────

_SEED_SPECS = [
    {
        "question": "Comment fait-on un engagement de dépense ?",
        "contenu": (
            "Pour créer un engagement de dépense, connectez-vous à SIREPA, "
            "accédez au menu Engagement > Nouvel engagement, renseignez les informations "
            "du prestataire (SIRET, nom), saisissez le montant HT, associez le bon de commande "
            "et transmettez pour validation par le responsable de service. "
            "L'engagement doit être réalisé avant toute commande ou prestation."
        ),
        "faq_visible": True,
        "tag": "engagement",
    },
    {
        "question": "Peut-on faire un engagement en monnaie étrangère ?",
        "contenu": (
            "Non. Les engagements de dépense doivent obligatoirement être libellés en euros. "
            "Pour les achats impliquant des devises étrangères, effectuez d'abord la conversion "
            "au taux de change officiel du jour, précisez le montant en devise dans les observations "
            "SIREPA et obtenez une autorisation écrite de la DFE (budget.dfe@onacvg.fr)."
        ),
        "faq_visible": True,
        "tag": "engagement",
    },
    {
        "question": "Ma facture n'est pas réglée, que faire ?",
        "contenu": (
            "Vérifiez que le service fait a été saisi et validé dans SIREPA, "
            "puis contactez le service facturation : sfact@onacvg.fr. "
            "Objet du mail : Relance fournisseur — N° facture [XXXXX]. "
            "Joindre la copie de l'engagement, la facture originale et le service fait. "
            "Délai de traitement : 5 jours ouvrés."
        ),
        "faq_visible": False,
        "tag": "facturation",
    },
]


@pytest.fixture(scope="module")
def faq_seed(db_schema):
    """Sème 3 réponses canoniques DFE en Postgres + Qdrant. Budget : 3 embeds Albert.

    Nettoyage complet (Qdrant + Postgres) au teardown du module.
    """
    from app.workers.feedback import feedback_job

    db = SessionLocal()
    seeded: list[SimpleNamespace] = []
    reponse_ids: list[str] = []

    with patch("app.workers.ingestion.broadcast_sync", lambda *a, **k: None):
        try:
            for spec in _SEED_SPECS:
                ticket = Ticket(
                    question=spec["question"],
                    domaine=DOMAINE,
                    statut_ticket="RÉPONDU",
                )
                db.add(ticket)
                db.flush()

                reponse = Reponse(
                    ticket_id=ticket.id,
                    contenu=spec["contenu"],
                    statut="VALIDÉE",
                    source="LLM",
                    canonique=True,
                    nb_validations=3,
                    faq_visible=spec["faq_visible"],
                    tag=spec["tag"],
                    validated_at=datetime.now(timezone.utc),
                )
                db.add(reponse)
                db.flush()
                db.commit()

                # Indexation dans Qdrant : 1 appel embed Albert par entrée
                feedback_job.run(str(reponse.id))

                rid = str(reponse.id)
                reponse_ids.append(rid)
                seeded.append(SimpleNamespace(
                    reponse_id=rid,
                    ticket_id=str(ticket.id),
                    question=spec["question"],
                    contenu=spec["contenu"],
                    faq_visible=spec["faq_visible"],
                    tag=spec["tag"],
                ))

            yield SimpleNamespace(
                engagement=seeded[0],
                monnaie=seeded[1],
                facture=seeded[2],
                domaine=DOMAINE,
                all=seeded,
            )

        finally:
            _nettoyer_qdrant_par_reponse_ids(reponse_ids)
            _nettoyer_postgres_reponses(db, reponse_ids)
            db.close()


# ── 6. Ingestion documents (module-scoped) ────────────────────────────────────


@pytest.fixture(scope="module")
def docs_ingeres(db_schema):
    """Ingère dfe_engagements.md et dfe_budget.md dans Qdrant.

    Budget Albert : ~10–15 appels embed (selon le nombre de chunks).
    Nettoyage par doc_id (filtre payload Qdrant) au teardown.
    """
    from app.workers.ingestion import ingestion_job

    doc_ids: list[str] = []
    tmp_paths: list[str] = []

    with patch("app.workers.ingestion.broadcast_sync", lambda *a, **k: None):
        try:
            for filename in ["dfe_engagements.md", "dfe_budget.md"]:
                src = FIXTURES_DIR / filename
                assert src.exists(), f"Fixture manquante : {src}"

                # Copie vers /tmp (ingestion_job supprimera le fichier après ingestion)
                tmp_path = str(Path(tempfile.gettempdir()) / f"qualite_{uuid.uuid4().hex}_{filename}")
                shutil.copy(str(src), tmp_path)

                doc_id = str(uuid.uuid4())
                doc_ids.append(doc_id)
                tmp_paths.append(tmp_path)

                # Ingestion synchrone : embed chunks + upsert Qdrant + enregistrement DB
                ingestion_job.run(
                    file_path=tmp_path,
                    filename=filename,
                    domaine=DOMAINE,
                    description=f"Document de test qualité RAG — {filename}",
                    doc_id=doc_id,
                )

            yield SimpleNamespace(
                doc_ids=doc_ids,
                domaine=DOMAINE,
                engagements_doc_id=doc_ids[0],
                budget_doc_id=doc_ids[1],
            )

        finally:
            _nettoyer_qdrant_par_doc_ids(doc_ids)
            # Postgres : les documents sont enregistrés par ingestion_job
            db = SessionLocal()
            try:
                for doc_id in doc_ids:
                    db.execute(text("DELETE FROM document_versions WHERE doc_id = :id"), {"id": doc_id})
                    db.execute(text("DELETE FROM document_uploads WHERE doc_id = :id"), {"id": doc_id})
                    db.execute(text("DELETE FROM documents WHERE doc_id = :id"), {"id": doc_id})
                db.commit()
            except Exception:
                db.rollback()
            finally:
                db.close()
            # Nettoyage du dossier de stockage permanent (créé par store_file)
            for doc_id in doc_ids:
                doc_dir = Path(settings.documents_storage_path) / doc_id
                if doc_dir.exists():
                    shutil.rmtree(str(doc_dir), ignore_errors=True)


# ── Utilitaires de nettoyage Qdrant ──────────────────────────────────────────


def _nettoyer_qdrant_par_reponse_ids(reponse_ids: list[str]) -> None:
    from qdrant_client.models import FieldCondition, Filter, MatchValue

    for rid in reponse_ids:
        try:
            qdrant_client.delete(
                collection_name=COLLECTION_NAME,
                points_selector=Filter(
                    must=[FieldCondition(key="reponse_id", match=MatchValue(value=rid))]
                ),
            )
        except Exception:
            pass


def _nettoyer_qdrant_par_doc_ids(doc_ids: list[str]) -> None:
    from qdrant_client.models import FieldCondition, Filter, MatchValue

    for doc_id in doc_ids:
        try:
            qdrant_client.delete(
                collection_name=COLLECTION_NAME,
                points_selector=Filter(
                    must=[FieldCondition(key="doc_id", match=MatchValue(value=doc_id))]
                ),
            )
        except Exception:
            pass


def _nettoyer_postgres_reponses(db, reponse_ids: list[str]) -> None:
    if not reponse_ids:
        return
    try:
        uuids = [uuid.UUID(r) for r in reponse_ids]
        db.execute(
            text("DELETE FROM reponse_chunks WHERE reponse_id = ANY(:ids)"),
            {"ids": uuids},
        )
        # Récupérer les ticket_ids avant de supprimer les réponses
        rows = db.execute(
            text("SELECT ticket_id FROM reponses WHERE id = ANY(:ids)"),
            {"ids": uuids},
        ).fetchall()
        ticket_ids = [r[0] for r in rows if r[0]]
        db.execute(
            text("DELETE FROM reponses WHERE id = ANY(:ids)"),
            {"ids": uuids},
        )
        if ticket_ids:
            db.execute(
                text("DELETE FROM tickets WHERE id = ANY(:ids)"),
                {"ids": ticket_ids},
            )
        db.commit()
    except Exception:
        db.rollback()
