from app.workers.celery_app import celery_app

@celery_app.task(
    name="ingestion_job",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    queue="queue_ingestion"
)
def ingestion_job(self, file_path: str, filename: str, domaine: str):
    try:
        print(f"[ingestion] Début traitement : {filename}")
        # Les étapes seront ajoutées Jour 8 et 9
        return {"status": "OK", "filename": filename}
    except Exception as exc:
        raise self.retry(exc=exc)