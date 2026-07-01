from app.services.search import search_hybrid
from app.workers.celery_app import celery_app

SEUIL_COSINUS = 0.50  # TEMPORAIRE — à recalibrer avec BGE-M3 réel sur Spark


@celery_app.task(
    name="question_job",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    queue="queue_questions",
)
def question_job(self, question: str, domaine: str, user_id: str | None = None):
    try:
        print("❓ --- NOUVELLE QUESTION ---")
        print(f"[QUESTION] Domaine  : {domaine}")
        print(f"[QUESTION] Question : {question}")

        # Étape 1 — Embedding + recherche hybride
        print("[QUESTION] Recherche hybride dans Qdrant...")
        chunks = search_hybrid(question, domaine, top_k=10)
        print(f"[QUESTION] {len(chunks)} chunks trouvés")

        for i, chunk in enumerate(chunks[:3]):
            print(
                f"[QUESTION] #{i+1} score_cosinus={chunk['score_cosinus']:.4f} score_rrf={chunk['score_rrf']:.4f} \
                    source={chunk['source']}"
            )

        return {
            "statut": "OK",
            "question": question,
            "domaine": domaine,
            "nb_chunks": len(chunks),
            "top_score_cosinus": chunks[0]["score_cosinus"] if chunks else 0,
            "top_score_rrf": chunks[0]["score_rrf"] if chunks else 0,
        }

    except Exception as exc:
        print(f"[QUESTION] ❌ Erreur : {exc}")
        raise self.retry(exc=exc) from exc
