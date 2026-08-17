import logging
from datetime import datetime, timedelta, timezone

import redis as redis_lib
from celery.signals import beat_init

from app.config import settings
from app.database import SessionLocal
from app.models.ticket import Ticket
from app.services.broadcast import broadcast_sync
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)

BEAT_HEARTBEAT_KEY = "ticketai:beat:heartbeat"
BEAT_STARTED_KEY = "ticketai:beat:started"


@beat_init.connect
def on_beat_init(**kwargs):
    try:
        r = redis_lib.from_url(settings.valkey_url, socket_connect_timeout=2)
        r.set(BEAT_STARTED_KEY, datetime.now(timezone.utc).isoformat(), ex=90000)
    except Exception:
        pass


@celery_app.task(name="app.workers.auto_cloture.auto_cloture_job", bind=True)
def auto_cloture_job(self):
    try:
        r = redis_lib.from_url(settings.valkey_url, socket_connect_timeout=2)
        r.set(BEAT_HEARTBEAT_KEY, datetime.now(timezone.utc).isoformat(), ex=90000)  # TTL 25h
    except Exception:
        pass

    seuil = datetime.now(timezone.utc) - timedelta(days=settings.jours_auto_cloture)
    db = SessionLocal()
    try:
        tickets = (
            db.query(Ticket)
            .filter(
                Ticket.statut_ticket == "VALIDÉ",
                Ticket.closed_at.is_(None),
                Ticket.validated_at.isnot(None),
                Ticket.validated_at < seuil,
            )
            .all()
        )

        now = datetime.now(timezone.utc)
        domaines: dict[str, list[str]] = {}
        for ticket in tickets:
            ticket.closed_at = now
            domaines.setdefault(ticket.domaine, []).append(str(ticket.id))

        db.commit()
    finally:
        db.close()

    for domaine, ids in domaines.items():
        for ticket_id in ids:
            broadcast_sync(f"sse:domain:{domaine}", "ticket_closed", {"ticket_id": ticket_id, "domaine": domaine})

    total = sum(len(v) for v in domaines.values())
    logger.info("%d ticket(s) clôturé(s) automatiquement.", total)
    return {"clotures": total}
