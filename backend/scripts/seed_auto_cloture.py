"""Ticket de test pour la fermeture automatique.

Insère un ticket VALIDÉ avec validated_at antérieur au seuil (default 7 jours)
pour permettre de tester auto_cloture_job sans attendre.

Usage :
    python -m scripts.seed_auto_cloture
"""

import uuid
from datetime import datetime, timedelta, timezone

from app.database import SessionLocal
from app.models.ticket import Ticket
from app.models.user import User

TICKET_ID = uuid.UUID("eeeeeeee-0000-0000-0000-000000000001")


def seed() -> None:
    db = SessionLocal()
    try:
        if db.query(Ticket).filter(Ticket.id == TICKET_ID).first():
            print("= Ticket de test auto-clôture existe déjà.")
            return

        # Utilise le premier utilisateur disponible comme créateur
        user = db.query(User).first()
        if not user:
            print("✗ Aucun utilisateur trouvé. Lance d'abord seed_validators.py.")
            return

        ticket = Ticket(
            id=TICKET_ID,
            question="Comment fonctionne la fermeture automatique des tickets ?",
            objet="[TEST] Auto-clôture",
            domaine="IT",
            user_id=user.id,
            statut_job="TERMINÉ",
            statut_ticket="VALIDÉ",
            validated_at=datetime.now(timezone.utc) - timedelta(days=10),
            processed_at=datetime.now(timezone.utc) - timedelta(days=10),
        )
        db.add(ticket)
        db.commit()
        print(f"+ Ticket test créé : {TICKET_ID}")
        print(f"  validated_at = {ticket.validated_at} (il y a 10 jours)")
        print("  Lance auto_cloture_job.delay() pour le clôturer.")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
