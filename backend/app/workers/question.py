from app.workers.celery_app import celery_app

@celery_app.task(
    name="question_job",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    queue="queue_questions"
)
def question_job(self, question: str, domaine: str, user_id: str | None = None):
    try:
        print(f"❓ --- NOUVELLE QUESTION ---")
        print(f"[QUESTION] Domaine  : {domaine}")
        print(f"[QUESTION] Question : {question}")

        return {
            "statut": "OK",
            "question": question,
            "domaine": domaine,
        }

    except Exception as exc:
        print(f"[QUESTION] ❌ Erreur : {exc}")
        raise self.retry(exc=exc) from exc