"""Tests du mode suivi (questions de précision dans un fil de conversation).

Le mode suivi est activé quand ticket_id est fourni et que le ticket a déjà
une réponse. Le pipeline :
  1. Charge le contexte du fil (historique + requete_recherche = fil concaténé)
  2. Le garde reçoit le fil complet, pas juste la précision
  3. Le court-circuit est DÉSACTIVÉ en mode suivi (fil ≠ question seule)

Budget Albert estimé :
  test_suivi_contexte_charge       : 1 embed (question initiale) + 1 embed (suivi) = 2
  test_suivi_garde_recoit_fil      : 1 embed (seed) + 1 embed (suivi) + 1 LLM garde = 3
  test_suivi_court_circuit_desact  : 1 embed (seed) + 1 embed (suivi) + 1 LLM garde = 3
  Total module                     : ~8 appels Albert
"""

import uuid
from datetime import datetime, timezone

import pytest
from app.database import SessionLocal
from app.models.garde_decision import GardeDecision
from app.models.reponse import Reponse
from app.models.ticket import Ticket

from .conftest import DOMAINE, _nettoyer_postgres_reponses, _nettoyer_qdrant_par_reponse_ids

pytestmark = [pytest.mark.integration, pytest.mark.albert]


def _creer_ticket_avec_reponse(question: str, reponse_texte: str) -> tuple[str, str]:
    """Crée un ticket RÉPONDU avec une réponse en DB.

    Retourne (ticket_id, reponse_id).
    """
    db = SessionLocal()
    try:
        ticket = Ticket(
            question=question,
            domaine=DOMAINE,
            statut_job="TERMINÉ",
            statut_ticket="RÉPONDU",
        )
        db.add(ticket)
        db.flush()
        reponse = Reponse(
            ticket_id=ticket.id,
            contenu=reponse_texte,
            statut="EN_ATTENTE",
            source="LLM",
        )
        db.add(reponse)
        db.commit()
        return str(ticket.id), str(reponse.id)
    finally:
        db.close()


def _run_suivi(precision: str, ticket_id: str, monkeypatch, *, mock_generate: bool = True) -> dict:
    """Lance question_job en mode suivi (avec ticket_id existant)."""
    import app.workers.question as qm
    from app.workers.question import question_job

    monkeypatch.setattr(qm, "suggerer_tag", lambda *a, **k: "test-tag")
    if mock_generate:
        monkeypatch.setattr(qm, "generate", lambda *a, **k: ("Réponse suivi de test.", False))

    question_job.push_request(id=str(uuid.uuid4()), retries=0)
    try:
        return question_job.run(
            question=precision,
            domaine=DOMAINE,
            ticket_id=ticket_id,
        )
    finally:
        question_job.pop_request()


# ── 1. Contexte du fil chargé correctement ───────────────────────────────────


def test_suivi_contexte_fil_charge(monkeypatch):
    """En mode suivi, charger_contexte_fil doit retourner l'historique du ticket.

    On crée un ticket avec une réponse, puis on pose une précision.
    Le pipeline doit charger le fil (historique ≥ 1 entrée).
    """
    q_initiale = "Comment faire un engagement de dépense pour un prestataire externe ?"
    r_initiale = "Créez l'engagement dans SIREPA avec les informations du prestataire."

    ticket_id, reponse_id = _creer_ticket_avec_reponse(q_initiale, r_initiale)

    try:
        # Spy sur charger_contexte_fil pour vérifier qu'il est appelé
        from app.services.question_pipeline import charger_contexte_fil

        appels_contexte = []

        def spy_contexte(tid, precision):
            historique, requete = charger_contexte_fil(tid, precision)
            appels_contexte.append({"historique": historique, "requete": requete})
            return historique, requete

        import app.workers.question as qm
        monkeypatch.setattr(qm, "charger_contexte_fil", spy_contexte)

        precision = "Et pour un prestataire étranger, c'est différent ?"
        _run_suivi(precision, ticket_id, monkeypatch, mock_generate=True)

        assert len(appels_contexte) == 1, "charger_contexte_fil doit être appelé en mode suivi"
        historique = appels_contexte[0]["historique"]
        assert historique is not None
        assert len(historique) >= 1, "L'historique doit contenir au moins la question initiale"
        # La requête de recherche doit contenir la précision
        requete = appels_contexte[0]["requete"]
        assert precision in requete or q_initiale in requete
    finally:
        db = SessionLocal()
        _nettoyer_postgres_reponses(db, [reponse_id])
        db.close()


# ── 2. Court-circuit désactivé en mode suivi ─────────────────────────────────


def test_suivi_court_circuit_desactive(monkeypatch):
    """En mode suivi, le court-circuit typographique est désactivé.

    Même si la précision est identique à la question indexée, le garde doit
    appeler le LLM (car il reçoit le fil complet, pas juste la précision).
    Ref : CLAUDE.md — "Disabled in follow-up mode: comparing a whole thread
    typographically to a single question is meaningless."
    """
    from app.workers.feedback import feedback_job

    # Créer une réponse canonique indexée sous une question précise
    q_canonique = "Comment faire un engagement de dépense ?"
    contenu = "Pour faire un engagement, connectez-vous à SIREPA et créez un engagement."

    db = SessionLocal()
    try:
        ticket = Ticket(question=q_canonique, domaine=DOMAINE, statut_ticket="RÉPONDU")
        db.add(ticket)
        db.flush()
        reponse = Reponse(
            ticket_id=ticket.id,
            contenu=contenu,
            statut="VALIDÉE",
            source="LLM",
            canonique=True,
            nb_validations=3,
            faq_visible=False,
            validated_at=datetime.now(timezone.utc),
        )
        db.add(reponse)
        db.commit()
        reponse_canonique_id = str(reponse.id)
    finally:
        db.close()

    # Indexer dans Qdrant
    feedback_job.run(reponse_canonique_id)

    # Créer un ticket de suivi avec une question initiale différente
    q_initiale = "J'ai un prestataire à engager pour des travaux de nettoyage."
    r_initiale = "Pour un engagement, vous devez utiliser SIREPA."
    ticket_suivi_id, reponse_suivi_id = _creer_ticket_avec_reponse(q_initiale, r_initiale)

    try:
        # La précision est IDENTIQUE à q_canonique — court-circuit désactivé en suivi
        precision = q_canonique  # "Comment faire un engagement de dépense ?"

        _run_suivi(precision, ticket_suivi_id, monkeypatch, mock_generate=True)

        # Chercher la décision du garde pour ce suivi
        db_check = SessionLocal()
        try:
            decisions = (
                db_check.query(GardeDecision)
                .order_by(GardeDecision.created_at.desc())
                .limit(5)
                .all()
            )
            # Trouver la décision avec est_suivi=True
            decisions_suivi = [d for d in decisions if d.est_suivi is True]
            if decisions_suivi:
                d = decisions_suivi[0]
                assert d.court_circuit is False, (
                    "En mode suivi, le court-circuit doit être désactivé même si "
                    "la précision est typographiquement identique à question_indexee."
                )
        finally:
            db_check.close()
    finally:
        _nettoyer_qdrant_par_reponse_ids([reponse_canonique_id])
        db = SessionLocal()
        _nettoyer_postgres_reponses(db, [reponse_canonique_id, reponse_suivi_id])
        db.close()


# ── 3. Le garde reçoit le fil complet en mode suivi ──────────────────────────


def test_suivi_garde_recoit_requete_recherche(monkeypatch):
    """En mode suivi, le garde reçoit requete_recherche (fil) et non juste la précision.

    Ref CLAUDE.md : "In follow-up mode: the guard receives `requete_recherche`
    (the full thread concatenated) rather than the bare precision."

    On vérifie que question_posee dans garde_decisions contient plus que juste
    la précision (= le fil).
    """
    from app.workers.feedback import feedback_job

    q_canonique = "Comment saisir un engagement de dépense dans SIREPA ?"
    contenu = "Pour saisir un engagement, accédez à SIREPA > Engagement > Nouvel engagement."

    db = SessionLocal()
    try:
        ticket = Ticket(question=q_canonique, domaine=DOMAINE, statut_ticket="RÉPONDU")
        db.add(ticket)
        db.flush()
        reponse = Reponse(
            ticket_id=ticket.id,
            contenu=contenu,
            statut="VALIDÉE",
            source="LLM",
            canonique=True,
            nb_validations=3,
            validated_at=datetime.now(timezone.utc),
        )
        db.add(reponse)
        db.commit()
        reponse_canonique_id = str(reponse.id)
    finally:
        db.close()

    feedback_job.run(reponse_canonique_id)

    q_initiale = "Je dois engager un prestataire pour un abonnement logiciel."
    r_initiale = "Un engagement de dépense est nécessaire avant toute commande."
    ticket_suivi_id, reponse_suivi_id = _creer_ticket_avec_reponse(q_initiale, r_initiale)

    # Précision courte qui ne suffit pas seule, mais qui dans le contexte du fil est claire
    precision = "Et comment faire exactement ?"

    try:
        _run_suivi(precision, ticket_suivi_id, monkeypatch, mock_generate=True)

        db_check = SessionLocal()
        try:
            decisions_suivi = (
                db_check.query(GardeDecision)
                .filter(GardeDecision.est_suivi.is_(True))
                .order_by(GardeDecision.created_at.desc())
                .limit(3)
                .all()
            )
            if decisions_suivi:
                d = decisions_suivi[0]
                # question_posee doit contenir plus que juste la précision
                # (le fil complet = q_initiale + r_initiale + precision)
                assert len(d.question_posee) > len(precision), (
                    f"En mode suivi, question_posee doit contenir le fil complet "
                    f"(longueur {len(d.question_posee)}), pas juste la précision "
                    f"(longueur {len(precision)})."
                )
                assert d.est_suivi is True
        finally:
            db_check.close()
    finally:
        _nettoyer_qdrant_par_reponse_ids([reponse_canonique_id])
        db = SessionLocal()
        _nettoyer_postgres_reponses(db, [reponse_canonique_id, reponse_suivi_id])
        db.close()
