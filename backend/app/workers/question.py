from app.services.search import search_hybrid
from app.workers.celery_app import celery_app

SEUIL_SIMILARITE = 0.92

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
        chunks = search_hybrid(question, domaine, top_k=10)
        print(f"[QUESTION] {len(chunks)} chunks trouvés")

        for i, chunk in enumerate(chunks[:3]):
            print(f"[QUESTION] #{i+1} score={chunk['score']:.4f} source={chunk['source']}")

        # Étape 2 — Branche canonique (Jour 13)
        # Étape 3 — Reranking (Jour 14)
        # Étape 4 — Génération LLM (Jour 14)

        return {
            "statut": "OK",
            "question": question,
            "domaine": domaine,
            "nb_chunks": len(chunks),
            "top_score": chunks[0]["score"] if chunks else 0,
        }

    except Exception as exc:
        print(f"[QUESTION] ❌ Erreur : {exc}")
        raise self.retry(exc=exc) from exc
