from celery import Celery
from celery.schedules import crontab
from celery.signals import setup_logging, task_prerun

from app.config import settings
from app.core.logs import configurer_logs, delier, lier

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
        "app.workers.retrait",
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


@setup_logging.connect
def _configurer_logs(**_):
    """Connected → Celery leaves logging alone (its -l flag included): same format and level as the API."""
    configurer_logs(settings.log_level)


@task_prerun.connect
def _lier_tache(task_id, task, **_):
    # Reset first: a pool thread runs task after task, the previous prefix must not leak into the next one.
    delier()
    lier(tache=f"{task.name.rsplit('.', 1)[-1]}:{task_id[:8]}")
