import uuid
from datetime import datetime, timezone

from celery.exceptions import Retry

from app.crud.question import TicketDisparu, upsert_reponse, upsert_ticket
from app.database import SessionLocal
from app.models.reponse_chunk import ReponseChunk
from app.models.ticket import Ticket
from app.services.garde_cache import statuer
from app.services.llm import generate
from app.services.question_pipeline import (
    SEUIL_COSINUS,  # noqa: F401 — ré-exporté pour les tests qui l'importent depuis ce module
    SEUIL_SUGGESTION,  # noqa: F401
    charger_contexte_fil,
    journaliser_garde,
    servir_reutilisation,
    ticket_existe,
    trouver_reponse_reutilisable,
)
from app.services.reranker import rerank
from app.services.search import search_hybrid
from app.workers.celery_app import celery_app

# Aliases privés maintenus pour la compatibilité des imports existants (tests, etc.)
_charger_contexte_fil = charger_contexte_fil
_upsert_reponse = upsert_reponse
_upsert_ticket = upsert_ticket
_ticket_existe = ticket_existe
_trouver_reponse_reutilisable = trouver_reponse_reutilisable
_servir_reutilisation = servir_reutilisation


@celery_app.task(
    name="question_job",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    queue="queue_questions",
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
        print("❓ --- NOUVELLE QUESTION ---")
        print(f"[QUESTION] Domaine  : {domaine}")
        print(f"[QUESTION] Question : {question}")

        job_id = uuid.UUID(self.request.id)
        user_uuid = uuid.UUID(user_id) if user_id else None

        ticket_uuid = uuid.UUID(ticket_id) if ticket_id else None
        est_suivi = ticket_uuid is not None and not retraiter
        question_suivi = question if est_suivi else None

        if ticket_uuid is not None and not ticket_existe(ticket_uuid):
            print(f"[QUESTION] ⏭️  Ticket {ticket_uuid} introuvable — job abandonné")
            return {"statut": "IGNORÉ", "raison": "TICKET_SUPPRIMÉ", "ticket_id": str(ticket_uuid)}

        # Étape 0 (suivi) — Charger le fil pour contextualiser recherche et LLM.
        historique: list[dict] | None = None
        requete_recherche = question
        if est_suivi:
            historique, requete_recherche = charger_contexte_fil(ticket_uuid, question)

        # Étape 1 — Embedding + recherche hybride
        print("[QUESTION] Recherche hybride dans Qdrant...")
        chunks = search_hybrid(question, domaine, top_k=15)
        print(f"[QUESTION] {len(chunks)} chunks trouvés")

        for i, chunk in enumerate(chunks[:3]):
            print(f"[QUESTION] #{i + 1} score_cosinus={chunk['score_cosinus']:.4f} source={chunk['source']}")

        top_score = chunks[0]["score_cosinus"] if chunks else 0.0

        # Étape 2 — Réponse déjà validée, retrouvée directement via son reponse_id.
        chunks_ctx: list[dict] | None = None
        db = SessionLocal()
        try:
            reponse_liee, score_liee, question_du_point = trouver_reponse_reutilisable(db, chunks)

            if reponse_liee is not None:
                print(f"[QUESTION] Score {score_liee:.4f} → réponse validée {reponse_liee.id}")

                if reponse_liee.canonique and score_liee >= SEUIL_COSINUS:
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
                            score_cosinus=score_liee,
                        )

                    if decision is not None and decision.verdict:
                        print("[QUESTION] Garde : OUI → CANONIQUE")
                        return servir_reutilisation(
                            db, job_id, ticket_uuid, question, domaine, user_uuid,
                            reponse_liee, score_liee, question_suivi, est_suivi,
                            self.request.retries, True, objet,
                        )
                    # Refus du garde → SUGGESTION, pas RAG. Le garde répond
                    # « pas la même demande », ce qui disqualifie le service sans
                    # revue — pas la proposition au relecteur. Sans ce repli, le
                    # système était non monotone : un candidat à 0,84 sortait en
                    # SUGGESTION sans être jugé, alors que le même à 0,86 était
                    # soumis au garde et, sur refus, renvoyé au RAG sans candidat.
                    # Franchir SEUIL_COSINUS dégradait donc l'issue. Le refus reste
                    # tracé dans `garde_decisions`.
                    print("[QUESTION] Garde : NON → SUGGESTION (revue humaine)")
                    return servir_reutilisation(
                        db, job_id, ticket_uuid, question, domaine, user_uuid,
                        reponse_liee, score_liee, question_suivi, est_suivi,
                        self.request.retries, False, objet,
                    )
                else:
                    return servir_reutilisation(
                        db, job_id, ticket_uuid, question, domaine, user_uuid,
                        reponse_liee, score_liee, question_suivi, est_suivi,
                        self.request.retries, False, objet,
                    )

        finally:
            db.close()

        # Étape 3 — Reranking
        if est_suivi:
            if chunks_ctx is None:
                chunks_ctx = search_hybrid(requete_recherche, domaine, top_k=15)
            chunks_rag = chunks_ctx
        else:
            chunks_rag = chunks
        print("[QUESTION] Reranking des chunks...")
        chunks_rerankes = rerank(requete_recherche, chunks_rag, top_k=5)
        for i, chunk in enumerate(chunks_rerankes):
            print(f"[QUESTION] Rerank #{i + 1} score={chunk['rerank_score']:.4f} source={chunk['source']}")

        # Étape 4 — Génération LLM (avec l'historique du fil pour un suivi)
        print("[QUESTION] Génération LLM...")
        hors_domaine = False
        try:
            reponse_texte, hors_domaine = generate(question, chunks_rerankes, historique=historique)
            suffix = " [HORS_DOMAINE]" if hors_domaine else ""
            print(f"[QUESTION] ✅ Réponse générée ({len(reponse_texte)} caractères){suffix}")
            statut_job = "TERMINÉ"
            erreur = None
        except Exception as llm_exc:
            print(f"[QUESTION] ❌ Erreur LLM : {llm_exc}")
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
                reponse = upsert_reponse(
                    db,
                    ticket,
                    reponse_texte,
                    top_score,
                    source="HORS_DOMAINE" if hors_domaine else "LLM",
                    question_suivi=question_suivi,
                    nouveau=est_suivi,
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

        print(f"[QUESTION] Ticket créé (id={ticket_id_str})")

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
        print(f"[QUESTION] ⏭️  Ticket {exc} supprimé en cours de traitement — job abandonné")
        return {"statut": "IGNORÉ", "raison": "TICKET_SUPPRIMÉ", "ticket_id": str(exc)}
    except Exception as exc:
        print(f"[QUESTION] ❌ Erreur : {exc}")
        raise self.retry(exc=exc) from exc
