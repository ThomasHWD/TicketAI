import uuid
from datetime import datetime, timezone

from app.database import SessionLocal
from app.models.reponse import Reponse
from app.models.ticket import Ticket
from app.services.llm import generate
from app.services.reranker import rerank
from app.services.search import search_hybrid
from app.workers.celery_app import celery_app

SEUIL_COSINUS = 0.48

@celery_app.task(
    name="question_job",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    queue="queue_questions"
)
def question_job(self, question: str, domaine: str, user_id: str | None = None):
    try:
        print("❓ --- NOUVELLE QUESTION ---")
        print(f"[QUESTION] Domaine  : {domaine}")
        print(f"[QUESTION] Question : {question}")

        # Étape 1 — Embedding + recherche hybride
        print("[QUESTION] Recherche hybride dans Qdrant...")
        chunks = search_hybrid(question, domaine, top_k=15)
        print(f"[QUESTION] {len(chunks)} chunks trouvés")

        for i, chunk in enumerate(chunks[:3]):
            print(f"[QUESTION] #{i+1} score_cosinus={chunk['score_cosinus']:.4f} source={chunk['source']}")

        top_score = chunks[0]["score_cosinus"] if chunks else 0.0

        # Étape 2 — Branche canonique
        if top_score >= SEUIL_COSINUS:
            print(f"[QUESTION] Score {top_score:.4f} ≥ seuil {SEUIL_COSINUS} → lookup PostgreSQL")
            db = SessionLocal()
            try:
                reponse_canonique = db.query(Reponse).filter(
                    Reponse.statut == "VALIDÉE"
                ).order_by(
                    Reponse.validated_at.desc()
                ).first()
            finally:
                db.close()

            if reponse_canonique:
                print("[QUESTION] ✅ Réponse canonique trouvée")
                return {
                    "statut": "OK",
                    "branche": "CANONIQUE",
                    "question": question,
                    "reponse": reponse_canonique.contenu,
                    "top_score_cosinus": top_score,
                }

        # Étape 3 — Reranking
        print("[QUESTION] Reranking des chunks...")
        chunks_rerankes = rerank(question, chunks, top_k=5)
        for i, chunk in enumerate(chunks_rerankes):
            print(f"[QUESTION] Rerank #{i+1} score={chunk['rerank_score']:.4f} source={chunk['source']}")

        # Étape 4 — Génération LLM
        print("[QUESTION] Génération LLM...")
        try:
            reponse_texte = generate(question, chunks_rerankes)
            print(f"[QUESTION] ✅ Réponse générée ({len(reponse_texte)} caractères)")
            statut_job = "TERMINÉ"
            erreur = None
        except Exception as llm_exc:
            print(f"[QUESTION] ❌ Erreur LLM : {llm_exc}")
            reponse_texte = None
            statut_job = "ÉCHOUÉ"
            erreur = str(llm_exc)

        # Étape 5 — Sauvegarde PostgreSQL
        db = SessionLocal()
        try:
            ticket = Ticket(
                id=uuid.uuid4(),
                question=question,
                domaine=domaine,
                user_id=uuid.UUID(user_id) if user_id else None,
                job_id=uuid.UUID(self.request.id),
                statut_job=statut_job,
                statut_ticket="RÉPONDU" if reponse_texte else "NOUVEAU",
                score_similarite=top_score,
                canonique=False,
                erreur=erreur,
                processed_at=datetime.now(timezone.utc),
            )
            db.add(ticket)
            db.flush()

            if reponse_texte:
                reponse = Reponse(
                    id=uuid.uuid4(),
                    ticket_id=ticket.id,
                    contenu=reponse_texte,
                    statut="EN_ATTENTE",
                    source="LLM",
                    score_similarite=top_score,
                )
                db.add(reponse)

            db.commit()
            db.refresh(ticket)
            ticket_id = str(ticket.id)
            reponse_id = str(reponse.id) if reponse_texte else None
        finally:
            db.close()

        print(f"[QUESTION] Ticket créé (id={ticket_id})")

        # Si LLM a échoué après sauvegarde → retry
        if statut_job == "ÉCHOUÉ":
            raise self.retry(
                exc=Exception(erreur),
                countdown=60
            )

        return {
            "statut": "OK",
            "branche": "RAG",
            "question": question,
            "domaine": domaine,
            "reponse": reponse_texte,
            "ticket_id": ticket_id,
            "reponse_id": reponse_id,
            "top_score_cosinus": top_score,
        }

    except Exception as exc:
        print(f"[QUESTION] ❌ Erreur : {exc}")
        raise self.retry(exc=exc) from exc
