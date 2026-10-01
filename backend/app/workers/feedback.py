import logging
import uuid

from celery.exceptions import Retry
from qdrant_client.models import PointStruct, SparseVector

from app.database import SessionLocal
from app.models.reponse import Reponse
from app.models.ticket import Ticket
from app.services.embedding import embed_texts
from app.services.garde_cache import statuer
from app.services.qdrant import COLLECTION_NAME, client
from app.services.question_pipeline import journaliser_garde
from app.services.reformulation import question_autonome
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


def get_response(db, reponse_id: str):
    response = db.query(Reponse).filter(Reponse.id == uuid.UUID(reponse_id)).first()
    if not response:
        raise ValueError(f"Réponse {reponse_id} introuvable")
    return response


def fil_jusqua(db, reponse: Reponse, ticket) -> list[str]:
    """User questions of the thread up to this follow-up included. Withdrawn turns skipped — a re-processed
    follow-up's obsolete draft carries the same question."""
    tours = (
        db.query(Reponse.question_suivi)
        .filter(
            Reponse.ticket_id == reponse.ticket_id,
            Reponse.question_suivi.isnot(None),
            Reponse.obsolete.is_(False),
            Reponse.created_at < reponse.created_at,
        )
        .order_by(Reponse.created_at.asc())
        .all()
    )
    return [ticket.question if ticket else "", *(t[0] for t in tours), reponse.question_suivi]


def question_indexable(tache, db, reponse: Reponse, ticket) -> str | None:
    """The question a response is indexed and judged under. A follow-up gets its self-contained rewrite (computed
    once, stored); its bare text is never indexed — out of context it matches any thread ending the same way."""
    if not reponse.question_suivi:
        return ticket.question if ticket else None
    if reponse.question_autonome:
        return reponse.question_autonome
    try:
        autonome = question_autonome(fil_jusqua(db, reponse, ticket))
    except Exception as exc:
        raise tache.retry(exc=RuntimeError(f"reformulation injoignable : {exc}")) from exc
    if autonome is None:
        logger.warning("Suivi %s non indexé : reformulation inexploitable", reponse.id)
        return None
    reponse.question_autonome = autonome
    db.commit()
    return autonome


def _alias_juge(tache, source, copie, nouvelle_question: str, ticket_source, domaine: str, db) -> bool:
    """Alias bypasses the guard at serving time (cosine ~1.0 → short-circuit, no judge) — verify equivalence before"""
    question_source = question_indexable(tache, db, source, ticket_source)
    if not question_source:
        # No question B to judge against — we don't grant the alias.
        logger.warning("Alias refusé : la réponse %s n'a aucune question indexable", source.id)
        return False

    decision = statuer(nouvelle_question, question_source)
    journaliser_garde(
        decision,
        job_id=None,
        ticket_id=copie.ticket_id,
        domaine=domaine,
        est_suivi=False,
        question_posee=nouvelle_question,
        question_indexee=question_source,
        reponse_id=source.id,
        # score_cosinus=None — this pair comes from a human gesture, not a search; 0.0 would read as a distant
        score_cosinus=None,
        score_lexical=None,
    )

    if decision.erreur:
        raise tache.retry(exc=RuntimeError(f"garde injoignable pour l'alias : {decision.erreur}"))
    if not decision.verdict:
        logger.info("Alias refusé par le garde pour la réponse %s", source.id)
    return decision.verdict


@celery_app.task(
    name="feedback_job",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    queue="queue_ingestion",
)
def feedback_job(self, responde_id: str, formulation_id: str | None = None):
    """Index a validated response under its question vector. formulation_id adds an alias point for a SUGGESTION"""
    db = SessionLocal()

    try:
        r = get_response(db, responde_id)

        ticket = db.query(Ticket).filter(Ticket.id == r.ticket_id).first()
        domaine = ticket.domaine if ticket else "NONE"

        # Index the question vector, not the response text — question↔question similarity reaches canonical thresholds
        r_content = r.contenu_corrige if r.contenu_corrige else r.contenu

        if formulation_id:
            copie = get_response(db, formulation_id)
            ticket_copie = db.query(Ticket).filter(Ticket.id == copie.ticket_id).first()
            texte_a_indexer = question_indexable(self, db, copie, ticket_copie)
            if not texte_a_indexer:
                return
            if not _alias_juge(self, r, copie, texte_a_indexer, ticket, domaine, db):
                return
            # distinct point derived from the copy — idempotent, leaves the original question point intact.
            point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{r.id}:{copie.id}"))
        elif r.question_suivi:
            texte_a_indexer = question_indexable(self, db, r, ticket)
            if not texte_a_indexer:
                return
            point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, str(r.id)))
        elif ticket and ticket.question:
            texte_a_indexer = ticket.question
            point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, str(r.id)))
        else:
            texte_a_indexer = r_content
            point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, str(r.id)))

        embeddings = embed_texts([texte_a_indexer])

        client.upsert(
            collection_name=COLLECTION_NAME,
            points=[
                PointStruct(
                    id=point_id,
                    vector={
                        "dense": embeddings[0]["dense"],
                        "sparse": SparseVector(
                            indices=embeddings[0]["sparse"]["indices"],
                            values=embeddings[0]["sparse"]["values"],
                        ),
                    },
                    payload={
                        "reponse_id": str(r.id),
                        "ticket_id": str(r.ticket_id),
                        "contenu": r_content,
                        "domaine": domaine,
                        # indexed question for this point — guard must judge the matched formulation, not the original
                        "question_indexee": texte_a_indexer,
                    },
                )
            ],
        )
    except Retry:
        raise
    except Exception as e:
        raise self.retry(exc=e) from e

    finally:
        db.close()
