"""Rejoue périodiquement les tickets bloqués en statut ÉCHOUÉ.

Cible : tickets sans réponse (statut_ticket = "NOUVEAU") dont le job a échoué
définitivement après ses 3 retries — typiquement un quota Albert épuisé ou une
indisponibilité transitoire. On ne touche pas aux suivis échoués (statut_ticket
!= "NOUVEAU") : la question de départ a déjà reçu une réponse, le suivi raté
est un cas distinct qui mérite une décision humaine.

Garde-fous :
- Âge maximal configurable (REPLAY_MAX_AGE_JOURS) : on ne ressort pas un ticket
  vieux de plusieurs semaines sans que l'utilisateur l'ait demandé.
- On remet statut_job à "EN_ATTENTE" *avant* d'envoyer dans la queue, pour que
  l'UI ne reste pas bloquée sur ÉCHOUÉ pendant le traitement.
- Si l'enqueue lève, on remet statut_job à "ÉCHOUÉ" et on passe au suivant.
"""

import logging
from datetime import datetime, timedelta, timezone

from app.config import settings
from app.database import SessionLocal
from app.models.ticket import Ticket
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="app.workers.replay_echoues.replay_echoues_job", bind=True)
def replay_echoues_job(self):
    seuil_age = datetime.now(timezone.utc) - timedelta(days=settings.replay_max_age_jours)

    db = SessionLocal()
    try:
        tickets = (
            db.query(Ticket)
            .filter(
                Ticket.statut_job == "ÉCHOUÉ",
                Ticket.statut_ticket == "NOUVEAU",
                Ticket.closed_at.is_(None),
                Ticket.created_at >= seuil_age,
            )
            .all()
        )

        a_rejouer = [
            {
                "id": str(t.id),
                "question": t.question,
                "domaine": t.domaine,
                "user_id": str(t.user_id) if t.user_id else None,
                "objet": t.objet,
            }
            for t in tickets
        ]

        for t in tickets:
            t.statut_job = "EN_ATTENTE"
        db.commit()
    finally:
        db.close()

    rejoues = 0
    for t in a_rejouer:
        try:
            celery_app.send_task(
                "question_job",
                args=[t["question"], t["domaine"], t["user_id"]],
                kwargs={"ticket_id": t["id"], "objet": t["objet"], "retraiter": True},
                queue="queue_questions",
            )
            rejoues += 1
        except Exception as exc:
            logger.error("Impossible de ré-enqueue le ticket %s : %s", t["id"], exc)
            db2 = SessionLocal()
            try:
                ticket = db2.query(Ticket).filter(Ticket.id == t["id"]).first()
                if ticket:
                    ticket.statut_job = "ÉCHOUÉ"
                    db2.commit()
            finally:
                db2.close()

    logger.info("%d ticket(s) ÉCHOUÉ(s) remis en queue sur %d trouvés.", rejoues, len(a_rejouer))
    return {"rejoues": rejoues, "trouves": len(a_rejouer)}
