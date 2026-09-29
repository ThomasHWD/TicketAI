import logging
import uuid
from datetime import datetime, timezone

from celery.exceptions import Retry

from app.crud.question import TicketDisparu, upsert_reponse, upsert_ticket
from app.database import SessionLocal
from app.models.reponse import Reponse
from app.models.reponse_chunk import ReponseChunk
from app.models.ticket import Ticket
from app.services.garde_cache import statuer
from app.services.llm import generate
from app.services.question_pipeline import (
    SEUIL_COSINUS,  # noqa: F401 — re-exported for tests that import from this module
    SEUIL_SUGGESTION,  # noqa: F401
    charger_contexte_fil,
    journaliser_garde,
    peut_servir_sans_revue,
    question_du_point_fiable,
    servir_reutilisation,
    ticket_existe,
    trouver_reponse_reutilisable,
)
from app.services.reranker import rerank
from app.services.search import search_hybrid
from app.services.tag_suggestion import suggerer_tag
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)

# Private aliases for backward-compatible imports (tests).
_charger_contexte_fil = charger_contexte_fil
_upsert_reponse = upsert_reponse
_upsert_ticket = upsert_ticket
_ticket_existe = ticket_existe
_trouver_reponse_reutilisable = trouver_reponse_reutilisable
_servir_reutilisation = servir_reutilisation


def _on_failure_question_job(self, exc, task_id, args, kwargs, einfo):
    """Mark ticket ÉCHOUÉ on permanent failure. Without this, a ticket replayed by replay_echoues_job stays"""
    ticket_id = kwargs.get("ticket_id")
    if not ticket_id:
        return
    import uuid as _uuid

    try:
        db = SessionLocal()
        try:
            ticket = db.query(Ticket).filter(Ticket.id == _uuid.UUID(ticket_id)).first()
            if ticket and ticket.statut_job == "EN_ATTENTE":
                ticket.statut_job = "ÉCHOUÉ"
                ticket.erreur = str(exc)
                db.commit()
        finally:
            db.close()
    except Exception:
        pass


@celery_app.task(
    name="question_job",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    queue="queue_questions",
    on_failure=_on_failure_question_job,
)
def question_job(
    self,
    question: str,
    domaine: str,
    user_id: str | None = None,
    ticket_id: str | None = None,
    objet: str | None = None,
    retraiter: bool = False,
):
    try:
        logger.info("nouvelle question — domaine=%s question=%s", domaine, question)

        job_id = uuid.UUID(self.request.id)
        user_uuid = uuid.UUID(user_id) if user_id else None

        ticket_uuid = uuid.UUID(ticket_id) if ticket_id else None
        est_suivi = ticket_uuid is not None and not retraiter
        question_suivi = question if est_suivi else None

        if ticket_uuid is not None and not _ticket_existe(ticket_uuid):
            logger.info("ticket %s introuvable — job abandonné", ticket_uuid)
            return {"statut": "IGNORÉ", "raison": "TICKET_SUPPRIMÉ", "ticket_id": str(ticket_uuid)}

        historique: list[dict] | None = None
        requete_recherche = question
        if est_suivi:
            historique, requete_recherche = charger_contexte_fil(ticket_uuid, question)

        logger.info("recherche hybride dans Qdrant...")
        # A follow-up is searched with its thread, for reuse and RAG alike: bare, « et pour un apprenti ? » never
        # reached the self-contained question it was validated under (cos 0.65 measured 28/09/2026, thread 0.98).
        chunks = search_hybrid(requete_recherche, domaine, top_k=15)
        logger.info("%d chunks trouvés", len(chunks))

        for i, chunk in enumerate(chunks[:3]):
            # both signals logged: the gate is a disjunction, reading one without the other is misleading.
            logger.debug(
                "#%d cosinus=%.4f lexical=%.2f/terme source=%s",
                i + 1,
                chunk["score_cosinus"],
                chunk.get("score_lexical", 0.0),
                chunk["source"],
            )

        top_score = chunks[0]["score_cosinus"] if chunks else 0.0

        db = SessionLocal()
        try:
            candidat = trouver_reponse_reutilisable(db, chunks)
            reponse_liee, score_liee = candidat.reponse, candidat.score_cosinus
            question_du_point = candidat.question_indexee

            if reponse_liee is not None:
                logger.info("score %.4f → réponse validée %s", score_liee, reponse_liee.id)

                # Guard called whenever its verdict changes the outcome — judged NON → RAG; Albert unreachable
                if peut_servir_sans_revue(reponse_liee) or candidat.servable:
                    # indexed question for this point — a response has one point per validated formulation.
                    question_indexee = question_du_point
                    # A follow-up point with no context is known unreliable, not unknown: treated as a refusal (RAG).
                    # As SUGGESTION it handed the reviewer the paternity answer to a bonus question (measured).
                    non_jugeable = False
                    if question_indexee and not question_du_point_fiable(db, reponse_liee, question_indexee):
                        logger.warning("point de suivi indexé sans contexte (réponse %s) — RAG", reponse_liee.id)
                        question_indexee, non_jugeable = None, True
                    elif not question_indexee:
                        if reponse_liee.question_suivi:
                            question_indexee = reponse_liee.question_autonome
                            non_jugeable = question_indexee is None
                        else:
                            ticket_source = db.query(Ticket).filter(Ticket.id == reponse_liee.ticket_id).first()
                            question_indexee = ticket_source.question if ticket_source else None
                    question_a_comparer = requete_recherche if est_suivi else question

                    decision = None
                    if question_indexee:
                        decision = statuer(question_a_comparer, question_indexee, est_suivi=est_suivi)
                        journaliser_garde(
                            decision,
                            job_id=job_id,
                            ticket_id=ticket_uuid,
                            domaine=domaine,
                            est_suivi=est_suivi,
                            question_posee=question_a_comparer,
                            question_indexee=question_indexee,
                            reponse_id=reponse_liee.id,
                            score_cosinus=candidat.score_cosinus,
                            score_lexical=candidat.score_lexical,
                        )

                    approuve = decision is not None and decision.verdict

                    if approuve and peut_servir_sans_revue(reponse_liee):
                        # OUI on a_relire → SUGGESTION (not CANONIQUE); servir_reutilisation checks it again.
                        logger.info("garde : OUI → CANONIQUE si le seuil est franchi, sinon SUGGESTION")
                        return servir_reutilisation(
                            db,
                            job_id,
                            ticket_uuid,
                            question,
                            domaine,
                            user_uuid,
                            reponse_liee,
                            score_liee,
                            question_suivi,
                            est_suivi,
                            self.request.retries,
                            True,
                            objet,
                            score_lexical=candidat.score_lexical or 0.0,
                        )

                    # Judged refusal → RAG; Albert unreachable → SUGGESTION. Network failure must not decide a branch.
                    refus_juge = non_jugeable or (decision is not None and not approuve and not decision.erreur)

                    if not refus_juge and candidat.servable:
                        logger.info(
                            "garde → SUGGESTION (revue humaine) : %s",
                            "OUI, mais réponse signalée a_relire ou non canonique"
                            if approuve
                            else (decision.erreur if decision else "aucune question indexée"),
                        )
                        return servir_reutilisation(
                            db,
                            job_id,
                            ticket_uuid,
                            question,
                            domaine,
                            user_uuid,
                            reponse_liee,
                            score_liee,
                            question_suivi,
                            est_suivi,
                            self.request.retries,
                            False,
                            objet,
                            score_lexical=candidat.score_lexical or 0.0,
                        )
                    logger.info("garde : NON → RAG (génération sur la question posée)")
                else:
                    # Lexical-only non-canonical → RAG whatever the verdict; only case where skipping the call is
                    logger.info("candidat lexical seul, non canonique → RAG (juge inutile)")

        finally:
            db.close()

        logger.info("reranking des chunks...")
        chunks_rerankes = rerank(requete_recherche, chunks, top_k=5)
        for i, chunk in enumerate(chunks_rerankes):
            logger.debug("rerank #%d score=%.4f source=%s", i + 1, chunk["rerank_score"], chunk["source"])

        logger.info("génération LLM...")
        hors_domaine = False
        try:
            reponse_texte, hors_domaine = generate(question, chunks_rerankes, historique=historique)
            suffix = " [HORS_DOMAINE]" if hors_domaine else ""
            logger.info("réponse générée (%d caractères)%s", len(reponse_texte), suffix)
            statut_job = "TERMINÉ"
            erreur = None
        except Exception as llm_exc:
            logger.error("erreur LLM : %s", llm_exc)
            reponse_texte = None
            statut_job = "ÉCHOUÉ"
            erreur = str(llm_exc)

        db = SessionLocal()
        try:
            ticket = upsert_ticket(
                db,
                job_id,
                ticket_id=ticket_uuid,
                question=question,
                objet=objet,
                domaine=domaine,
                user_id=user_uuid,
                statut_job=statut_job,
                statut_ticket="RÉPONDU" if reponse_texte else "NOUVEAU",
                score_similarite=top_score,
                canonique=False,
                nb_retries=self.request.retries,
                erreur=erreur,
                processed_at=datetime.now(timezone.utc),
            )

            reponse_id = None
            if reponse_texte:
                if hors_domaine:
                    tag_suggere = None
                else:
                    rows = (
                        db.query(Reponse.tag)
                        .join(Ticket, Ticket.id == Reponse.ticket_id)
                        .filter(
                            Reponse.tag.isnot(None),
                            Reponse.canonique.is_(True),
                            Reponse.reponse_source_id.is_(None),
                            Reponse.obsolete.is_(False),
                            Ticket.domaine == domaine,
                        )
                        .distinct()
                        .all()
                    )
                    tags_existants = sorted(r.tag for r in rows) or None
                    tag_suggere = suggerer_tag(question, reponse_texte, db, tags_existants)
                reponse = upsert_reponse(
                    db,
                    ticket,
                    reponse_texte,
                    top_score,
                    source="HORS_DOMAINE" if hors_domaine else "LLM",
                    question_suivi=question_suivi,
                    nouveau=est_suivi,
                    tag=tag_suggere,
                )
                reponse_id = str(reponse.id)

                for chunk in chunks_rerankes if not hors_domaine else []:
                    if not chunk.get("doc_id"):
                        continue
                    rc = ReponseChunk(
                        id=uuid.uuid4(),
                        reponse_id=reponse.id,
                        doc_id=chunk.get("doc_id"),
                        chunk_index=chunk.get("chunk_index", 0),
                        version=chunk.get("version"),
                        score_cosinus=chunk.get("score_cosinus"),
                        rerank_score=chunk.get("rerank_score"),
                    )
                    db.add(rc)

            ticket_id_str = str(ticket.id)
            db.commit()
        finally:
            db.close()

        logger.info("ticket créé (id=%s)", ticket_id_str)

        if statut_job == "ÉCHOUÉ":
            raise self.retry(exc=Exception(erreur), countdown=60)

        if statut_job == "TERMINÉ":
            from app.services.broadcast import broadcast_sync

            event = "ticket_followup" if est_suivi else "ticket_answered"
            broadcast_sync(f"sse:domain:{domaine}", event, {"ticket_id": ticket_id_str, "domaine": domaine})
            if user_uuid:
                broadcast_sync(f"sse:user:{user_uuid}", event, {"ticket_id": ticket_id_str, "domaine": domaine})

        return {
            "statut": "OK",
            "branche": "RAG",
            "question": question,
            "domaine": domaine,
            "reponse": reponse_texte,
            "ticket_id": ticket_id_str,
            "reponse_id": reponse_id,
            "top_score_cosinus": top_score,
        }

    except Retry:
        raise
    except TicketDisparu as exc:
        logger.info("ticket %s supprimé en cours de traitement — job abandonné", exc)
        return {"statut": "IGNORÉ", "raison": "TICKET_SUPPRIMÉ", "ticket_id": str(exc)}
    except Exception as exc:
        logger.error("erreur question_job : %s", exc)
        raise self.retry(exc=exc) from exc
