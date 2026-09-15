"""Tests du workflow bout-en-bout : RAG → validation → canonique → FAQ.

Ces tests simulent le cycle de vie complet d'une réponse :
  1. Question posée → branche RAG
  2. Réponse validée → nb_validations augmente
  3. Après 3 validations → canonique=True → indexée dans Qdrant
  4. Question similaire suivante → branche CANONIQUE
  5. Canonique + faq_visible=True → visible dans la FAQ

Chaque test est autonome : il crée ses propres données et nettoie après.
Budget Albert :
  test_rag_puis_validation          : 1 embed + 1 rerank + 1 LLM = 3 appels
  test_canonisation_directe_faq     : 1 feedback embed + 1 FAQ embed = 2 appels
  test_question_similaire_canonique : 2 embeds (seed + question) + 1 LLM garde = 3 appels
  test_reponse_source_id_suggestion : 1 embed (seed) + 1 embed (query) + 0-1 LLM = 2-3 appels
  Total module                      : ~10–11 appels Albert
"""

import uuid
from datetime import datetime, timezone

import pytest
from app.database import SessionLocal
from app.models.reponse import Reponse
from app.models.ticket import Ticket
from app.services.faq import rechercher_faq
from app.services.qdrant import COLLECTION_NAME
from app.services.qdrant import client as qdrant_client

from .conftest import DOMAINE, _nettoyer_postgres_reponses, _nettoyer_qdrant_par_reponse_ids, run_question

pytestmark = [pytest.mark.integration, pytest.mark.albert]


def _creer_reponse_canonique(question: str, contenu: str, faq_visible: bool = True) -> tuple[str, str]:
    """Crée un ticket + réponse canonique en DB et l'indexe dans Qdrant.

    Retourne (reponse_id, ticket_id) pour le nettoyage.
    Budget : 1 appel embed Albert (feedback_job.run).
    """
    from app.workers.feedback import feedback_job

    db = SessionLocal()
    try:
        ticket = Ticket(question=question, domaine=DOMAINE, statut_ticket="RÉPONDU")
        db.add(ticket)
        db.flush()
        reponse = Reponse(
            ticket_id=ticket.id,
            contenu=contenu,
            statut="VALIDÉE",
            source="LLM",
            canonique=True,
            nb_validations=3,
            faq_visible=faq_visible,
            tag="engagement",
            validated_at=datetime.now(timezone.utc),
        )
        db.add(reponse)
        db.commit()
        reponse_id = str(reponse.id)
        ticket_id = str(ticket.id)
    finally:
        db.close()

    feedback_job.run(reponse_id)
    return reponse_id, ticket_id


# ── 1. RAG → validation → nb_validations correct ─────────────────────────────


def test_rag_puis_validation_manuelle(db_schema, monkeypatch):
    """question_job produit une réponse RAG, la validation met à jour nb_validations.

    On simule la validation directement en DB (sans passer par l'API REST)
    pour tester la mécanique métier indépendamment du routing HTTP.
    """
    q = "Quelle est la procédure pour établir un ordre de mission ?"

    # mock_generate=True : ce test vérifie la mécanique de validation, pas la qualité LLM.
    res = run_question(q, DOMAINE, monkeypatch, mock_tag=True, mock_generate=True)
    assert res["branche"] in ("RAG", "HORS_DOMAINE")

    reponse_id = res.get("reponse_id")
    if not reponse_id:
        pytest.skip("Pas de reponse_id retourné (HORS_DOMAINE sans contenu)")

    # Simule une première validation
    db = SessionLocal()
    try:
        r = db.query(Reponse).filter(Reponse.id == uuid.UUID(reponse_id)).first()
        assert r is not None
        r.nb_validations = 1
        r.statut = "VALIDÉE"
        r.validated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(r)
        assert r.nb_validations == 1
        assert r.statut == "VALIDÉE"
        assert r.canonique is False  # pas encore canonique
    finally:
        db.close()


# ── 2. Canonisation directe + indexation Qdrant ───────────────────────────────


def test_canonisation_et_indexation_qdrant(monkeypatch):
    """Une réponse canonisée (nb_validations=3) doit être trouvable dans Qdrant.

    feedback_job.run() indexe la réponse sous le vecteur de la question.
    Le point Qdrant doit avoir reponse_id dans son payload.
    """
    from qdrant_client.models import FieldCondition, Filter, MatchValue

    q = "Comment remplir un certificat administratif pour un service fait ?"
    contenu = "Le certificat administratif est disponible sur l'intranet ONAC-VG."

    reponse_id, ticket_id = _creer_reponse_canonique(q, contenu)

    try:
        # Chercher le point dans Qdrant
        results = qdrant_client.scroll(
            collection_name=COLLECTION_NAME,
            scroll_filter=Filter(
                must=[FieldCondition(key="reponse_id", match=MatchValue(value=reponse_id))]
            ),
            limit=1,
            with_payload=True,
        )
        points = results[0]
        assert len(points) == 1, (
            f"Le point Qdrant pour reponse_id={reponse_id} est introuvable. "
            "Vérifier que feedback_job.run() a bien été appelé."
        )
        payload = points[0].payload
        assert payload.get("reponse_id") == reponse_id
        assert payload.get("question_indexee") == q
    finally:
        _nettoyer_qdrant_par_reponse_ids([reponse_id])
        db = SessionLocal()
        _nettoyer_postgres_reponses(db, [reponse_id])
        db.close()


# ── 3. Canonique → visible dans la FAQ ───────────────────────────────────────


def test_canonique_visible_dans_faq(monkeypatch):
    """Une réponse canonique + faq_visible=True apparaît dans la FAQ.

    Cycle complet : créer → indexer → rechercher via FAQ.
    Budget : 1 embed (feedback_job) + 1 embed (FAQ search).
    """
    q = "Comment faire un engagement de dépense pour la médecine de prévention ?"
    contenu = "Oui, un engagement est obligatoire. Code action : Médecine de prévention."

    reponse_id, ticket_id = _creer_reponse_canonique(q, contenu, faq_visible=True)

    try:
        db = SessionLocal()
        try:
            rangs = rechercher_faq(db, q, limite=5)
            ids_resultats = {r["reponse_id"] for r in rangs["resultats"]}
            assert reponse_id in ids_resultats, (
                f"La réponse canonique faq_visible=True doit être dans resultats. "
                f"IDs trouvés : {ids_resultats}"
            )
        finally:
            db.close()
    finally:
        _nettoyer_qdrant_par_reponse_ids([reponse_id])
        db = SessionLocal()
        _nettoyer_postgres_reponses(db, [reponse_id])
        db.close()


# ── 4. Canonique non-visible → absente de la FAQ ─────────────────────────────


def test_canonique_non_visible_absent_faq(monkeypatch):
    """faq_visible=False → absente même si canonique et indexée."""
    q = "Comment obtenir un remboursement de frais de déplacement ?"
    contenu = "Contacter missions-deplacements@onacvg.fr avec votre ordre de mission."

    reponse_id, ticket_id = _creer_reponse_canonique(q, contenu, faq_visible=False)

    try:
        db = SessionLocal()
        try:
            rangs = rechercher_faq(db, q, limite=5)
            tous_ids = (
                {r["reponse_id"] for r in rangs["resultats"]}
                | {r["reponse_id"] for r in rangs["incertains"]}
            )
            assert reponse_id not in tous_ids, (
                "faq_visible=False doit cacher la réponse même si elle est canonique et indexée."
            )
        finally:
            db.close()
    finally:
        _nettoyer_qdrant_par_reponse_ids([reponse_id])
        db = SessionLocal()
        _nettoyer_postgres_reponses(db, [reponse_id])
        db.close()


# ── 5. Réponse canonique → question similaire → CANONIQUE ────────────────────


def test_question_similaire_servie_canonique(monkeypatch):
    """Après canonisation, une question similaire est servie en CANONIQUE.

    Budget : 1 embed (seed feedback_job) + 1 embed + 1 LLM garde (question similaire).
    """
    q_original = "Comment saisir un engagement de dépense dans SIREPA ?"
    q_similaire = "Comment fait-on un engagement de dépense dans SIREPA ?"
    contenu = "Pour saisir un engagement dans SIREPA : menu Engagement > Nouvel engagement."

    reponse_id, ticket_id = _creer_reponse_canonique(q_original, contenu)

    try:
        res = run_question(q_similaire, DOMAINE, monkeypatch, mock_tag=True)

        assert res["branche"] in ("CANONIQUE", "SUGGESTION"), (
            f"Une question similaire à un canonique doit être CANONIQUE ou SUGGESTION. "
            f"Obtenu : {res['branche']}"
        )
    finally:
        _nettoyer_qdrant_par_reponse_ids([reponse_id])
        db = SessionLocal()
        _nettoyer_postgres_reponses(db, [reponse_id])
        db.close()
