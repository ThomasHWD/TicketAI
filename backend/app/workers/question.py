from app.services.search import search_hybrid
from app.workers.celery_app import celery_app
from app.database import SessionLocal
from app.models.reponse import Reponse

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

        top_score = chunks[0]["score_cosinus"] if chunks else 0.0

        # Etape 2 - Lookup PostgreSQL branche canonique
        reponse_canonique = None
        if top_score >= SEUIL_COSINUS:
            print(
                f"[QUESTION] Score {top_score:.4f} ≥ seuil {SEUIL_COSINUS} → lookup PostgreSQL"
            )
            doc_id = chunks[0].get("doc_id")

            db = SessionLocal()
            try:
                reponse_canonique = (
                    db.query(Reponse)
                    .filter(Reponse.statut == "VALIDÉE")
                    .order_by(Reponse.validated_at.desc())
                    .first()
                )
            finally:
                db.close()

        if reponse_canonique:
            print(f"[QUESTION] ✅ Réponse canonique trouvée — pas d'appel LLM")
            return {
                "statut": "OK",
                "branche": "CANONIQUE",
                "question": question,
                "reponse": reponse_canonique.contenu,
                "top_score_cosinus": top_score,
            }

        # Étape 3 — Reranking (Jour 14)
        # Étape 4 — Génération LLM (Jour 14)
        print(
            f"[QUESTION] Score {top_score:.4f} < seuil ou pas de réponse validée → pipeline RAG"
        )
        return {
            "statut": "OK",
            "branche": "RAG",
            "question": question,
            "domaine": domaine,
            "nb_chunks": len(chunks),
            "top_score_cosinus": top_score,
        }

    except Exception as exc:
        print(f"[QUESTION] ❌ Erreur : {exc}")
        raise self.retry(exc=exc) from exc
