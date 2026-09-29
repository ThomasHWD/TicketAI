"""Re-examines the responses a document deletion withdrew, and puts back those the remaining sources fully support.

The deletion has already withdrawn them: until this job decides, nothing is served. Every path other than an explicit
SOUTENUE verdict leaves them withdrawn, with the reason shown in the Obsolètes tab."""

import logging
import uuid

from app.database import SessionLocal
from app.models.reponse import Reponse
from app.services.broadcast import broadcast_sync
from app.services.obsolescence import RAISON_SUPPRESSION, fermeture_copies, remettre_en_service
from app.services.retrait import (
    MAX_REEXAMENS,
    VERDICT_SOUTENUE,
    appuye_d_abord_sur,
    encore_en_vigueur,
    juger_retrait,
    question_de,
)
from app.services.reverification import tracer
from app.workers.celery_app import celery_app
from app.workers.feedback import feedback_job

logger = logging.getLogger(__name__)

JUSTIF_SOURCE_PRINCIPALE = "Le document supprimé était sa source principale."
JUSTIF_SANS_RESTE = "Aucune autre source de cette réponse n'est encore en vigueur."
JUSTIF_BUDGET = "Non réexaminée : trop de réponses touchées par cette suppression."
JUSTIF_PANNE = "Non réexaminée : le modèle de vérification était indisponible."


def _retiree_par(r: Reponse | None, doc_id: str) -> bool:
    """Still withdrawn by this very deletion — a human may have restored, edited or deleted it in the meantime."""
    return r is not None and r.obsolete and r.obsolete_raison == RAISON_SUPPRESSION and r.obsolete_doc_id == doc_id


@celery_app.task(name="reexamen_retrait_job", bind=True, queue="queue_questions")
def reexamen_retrait_job(self, doc_id: str, examens: list[dict]):
    """`examens`: [{reponse_id, passages_retires, passages_restants}] — both read by the route before the withdrawal
    deleted the points they come from."""
    db = SessionLocal()
    remises = maintenues = 0
    budget = MAX_REEXAMENS
    panne = False
    domaines: set[str] = set()
    try:
        for examen in examens:
            racine = db.query(Reponse).filter(Reponse.id == uuid.UUID(examen["reponse_id"])).first()
            if not _retiree_par(racine, doc_id):
                continue
            famille = [
                r
                for r in db.query(Reponse).filter(Reponse.id.in_(fermeture_copies(db, {racine.id}))).all()
                if _retiree_par(r, doc_id)
            ]

            justification = None
            if panne:
                justification = JUSTIF_PANNE
            elif appuye_d_abord_sur(db, racine, doc_id):
                justification = JUSTIF_SOURCE_PRINCIPALE
            elif budget <= 0:
                justification = JUSTIF_BUDGET
            if justification:
                tracer(db, famille, justification, None)
                maintenues += 1
                continue

            question = question_de(db, racine)
            restants = encore_en_vigueur(db, examen.get("passages_restants") or [])
            if not question or not restants:
                tracer(db, famille, JUSTIF_SANS_RESTE, None)
                maintenues += 1
                continue

            budget -= 1
            try:
                verdict, motif = juger_retrait(
                    question, racine.contenu_corrige or racine.contenu, examen.get("passages_retires") or [], restants
                )
            except Exception as exc:
                logger.error("réexamen après suppression impossible (%s) — réponses maintenues retirées", exc)
                panne = True
                tracer(db, famille, JUSTIF_PANNE, None)
                maintenues += 1
                continue

            logger.info("%s → %s (%s)", racine.id, verdict, motif)
            if verdict != VERDICT_SOUTENUE:
                tracer(db, famille, motif, None)
                maintenues += 1
                continue

            # only the members this deletion withdrew, and only reviewed ones: a pending copy was sent back to the
            # pipeline and has been answered again since
            a_remettre = [r for r in famille if r.statut in ("VALIDÉE", "CORRIGÉE")]
            for r in a_remettre:
                r.analyse_justification = None
                r.analyse_extraits = None
            for args in remettre_en_service(db, a_remettre):
                feedback_job.apply_async(args=args, queue="queue_ingestion")
            remises += 1
            if racine.ticket:
                domaines.add(racine.ticket.domaine)
    finally:
        db.close()

    logger.info(
        "suppression de %s : %d réponse(s) remise(s) en service, %d maintenue(s) retirée(s)",
        doc_id,
        remises,
        maintenues,
    )
    if remises:
        broadcast_sync("sse:admin", "saved_answers_updated", {"doc_id": doc_id})
        for domaine in domaines:
            broadcast_sync(f"sse:domain:{domaine}", "saved_answers_updated", {"doc_id": doc_id})
    return {"doc_id": doc_id, "remises": remises, "maintenues": maintenues}
