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
    SEUIL_COSINUS,  # noqa: F401 — ré-exporté pour les tests qui l'importent depuis ce module
    SEUIL_SUGGESTION,  # noqa: F401
    charger_contexte_fil,
    journaliser_garde,
    peut_servir_sans_revue,
    servir_reutilisation,
    ticket_existe,
    trouver_reponse_reutilisable,
)
from app.services.reranker import rerank
from app.services.search import search_hybrid
from app.services.tag_suggestion import suggerer_tag
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)

# Aliases privés maintenus pour la compatibilité des imports existants (tests, etc.)
_charger_contexte_fil = charger_contexte_fil
_upsert_reponse = upsert_reponse
_upsert_ticket = upsert_ticket
_ticket_existe = ticket_existe
_trouver_reponse_reutilisable = trouver_reponse_reutilisable
_servir_reutilisation = servir_reutilisation


def _on_failure_question_job(self, exc, task_id, args, kwargs, einfo):
    """Si le task échoue définitivement avec un ticket_id, le repasse à ÉCHOUÉ.

    Sans ce hook, un ticket rejoué par replay_echoues_job (statut_job=EN_ATTENTE)
    et qui échoue avant l'étape upsert_ticket reste bloqué à EN_ATTENTE pour
    toujours — invisible au filtre du prochain replay qui cible ÉCHOUÉ.
    """
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

        # Étape 0 (suivi) — Charger le fil pour contextualiser recherche et LLM.
        historique: list[dict] | None = None
        requete_recherche = question
        if est_suivi:
            historique, requete_recherche = charger_contexte_fil(ticket_uuid, question)

        # Étape 1 — Embedding + recherche hybride
        logger.info("recherche hybride dans Qdrant...")
        chunks = search_hybrid(question, domaine, top_k=15)
        logger.info("%d chunks trouvés", len(chunks))

        for i, chunk in enumerate(chunks[:3]):
            # Les deux signaux sont tracés : la porte se franchit par l'un ou
            # l'autre, donc lire les journaux exige de voir les deux.
            logger.debug(
                "#%d cosinus=%.4f lexical=%.2f/terme source=%s",
                i + 1, chunk["score_cosinus"], chunk.get("score_lexical", 0.0), chunk["source"],
            )

        top_score = chunks[0]["score_cosinus"] if chunks else 0.0

        # Étape 2 — Réponse déjà validée, retrouvée directement via son reponse_id.
        chunks_ctx: list[dict] | None = None
        db = SessionLocal()
        try:
            candidat = trouver_reponse_reutilisable(db, chunks)
            reponse_liee, score_liee = candidat.reponse, candidat.score_cosinus
            question_du_point = candidat.question_indexee

            if reponse_liee is not None:
                logger.info("score %.4f → réponse validée %s", score_liee, reponse_liee.id)

                # `peut_servir_sans_revue` plutôt que `.canonique` : une réponse
                # signalée `a_relire` ne franchira pas la porte de
                # `servir_reutilisation` de toute façon, autant ne pas payer un
                # appel au juge pour elle. On retombe sur `elif candidat.servable`
                # → SUGGESTION, sous revue humaine.
                if peut_servir_sans_revue(reponse_liee) and candidat.franchit(SEUIL_COSINUS):
                    # La question portée par le point qui a matché fait foi : une
                    # réponse est indexée sous autant de formulations qu'elle a de
                    # validations humaines, et le garde doit juger celle-là. Repli
                    # sur le ticket d'origine pour les points antérieurs, qui ne
                    # portent pas encore `question_indexee` dans leur payload.
                    question_indexee = question_du_point
                    if not question_indexee:
                        ticket_source = db.query(Ticket).filter(Ticket.id == reponse_liee.ticket_id).first()
                        question_indexee = reponse_liee.question_suivi or (
                            ticket_source.question if ticket_source else None
                        )
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
                            # Les deux signaux séparément : le cosinus garde le
                            # sens qu'il avait avant BM25, ce qui rend les décisions
                            # comparables d'une version à l'autre, et le lexical dit
                            # par quelle porte le candidat est passé.
                            score_cosinus=candidat.score_cosinus,
                            score_lexical=candidat.score_lexical,
                        )

                    if decision is not None and decision.verdict:
                        logger.info("garde : OUI → CANONIQUE")
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
                    # Refus du garde → SUGGESTION, pas RAG. Le garde répond
                    # « pas la même demande », ce qui disqualifie le service sans
                    # revue — pas la proposition au relecteur. Sans ce repli, le
                    # système était non monotone : un candidat à 0,84 sortait en
                    # SUGGESTION sans être jugé, alors que le même à 0,86 était
                    # soumis au garde et, sur refus, renvoyé au RAG sans candidat.
                    # Franchir SEUIL_COSINUS dégradait donc l'issue. Le refus reste
                    # tracé dans `garde_decisions`.
                    #
                    # Sauf si le candidat n'est entré que par la porte lexicale :
                    # le juge vient de le refuser et rien d'autre ne le soutient,
                    # le proposer à un relecteur serait lui montrer du bruit.
                    if candidat.servable:
                        logger.info("garde : NON → SUGGESTION (revue humaine)")
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
                    logger.info("garde : NON + candidat lexical seul → RAG")
                elif candidat.servable:
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
                else:
                    # Candidat retenu par les seuls mots, et non canonique : aucun
                    # juge ne le verra, donc il ne doit pas être proposé.
                    logger.info("candidat lexical seul, non canonique → RAG")

        finally:
            db.close()

        # Étape 3 — Reranking
        if est_suivi:
            if chunks_ctx is None:
                chunks_ctx = search_hybrid(requete_recherche, domaine, top_k=15)
            chunks_rag = chunks_ctx
        else:
            chunks_rag = chunks
        logger.info("reranking des chunks...")
        chunks_rerankes = rerank(requete_recherche, chunks_rag, top_k=5)
        for i, chunk in enumerate(chunks_rerankes):
            logger.debug("rerank #%d score=%.4f source=%s", i + 1, chunk["rerank_score"], chunk["source"])

        # Étape 4 — Génération LLM (avec l'historique du fil pour un suivi)
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

        # Étape 5 — Sauvegarde PostgreSQL + enregistrement chunks
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

                for chunk in chunks_rerankes:
                    if not chunk.get("doc_id"):
                        continue
                    rc = ReponseChunk(
                        id=uuid.uuid4(),
                        reponse_id=reponse.id,
                        doc_id=chunk.get("doc_id"),
                        chunk_index=chunk.get("chunk_index", 0),
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
