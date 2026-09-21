from celery import Celery
from celery.schedules import crontab

from app.config import settings

celery_app = Celery(
    "ticketai",
    broker=settings.valkey_url,
    backend=settings.valkey_url,
    include=[
        "app.workers.ingestion",
        "app.workers.document_update",
        "app.workers.question",
        "app.workers.feedback",
        "app.workers.reverification",
        "app.workers.confrontation",
        "app.workers.auto_cloture",
        "app.workers.replay_echoues",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_max_tasks_per_child=1000,
    result_extended=True,
    task_queues={
        "queue_questions": {"exchange": "queue_questions"},
        "queue_ingestion": {"exchange": "queue_ingestion"},
    },
    task_default_queue="queue_questions",
    worker_pool="threads",
    beat_schedule={
        "auto-cloture-tickets": {
            "task": "app.workers.auto_cloture.auto_cloture_job",
            "schedule": crontab(hour=2, minute=0),
        },
        "replay-tickets-echoues": {
            "task": "app.workers.replay_echoues.replay_echoues_job",
            "schedule": crontab(minute=0),  # toutes les heures
        },
    },
)
