import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from app.core.security import CurrentUser
from app.database import SessionLocal
from app.models.notification import Notification

router = APIRouter()


@router.get("/notifications")
async def mes_notifications(current_user: CurrentUser):
    """Notifications de l'utilisateur courant, les plus récentes en premier."""
    db = SessionLocal()
    try:
        notifications = (
            db.query(Notification)
            .filter(Notification.user_id == current_user.id, Notification.read_at.is_(None))
            .order_by(Notification.created_at.desc())
            .limit(50)
            .all()
        )
        return [_serialize(n) for n in notifications]
    finally:
        db.close()


@router.post("/notifications/{notification_id}/lire", status_code=204)
async def marquer_lue(notification_id: str, current_user: CurrentUser):
    """Marque une notification comme lue (idempotent)."""
    try:
        nid = uuid.UUID(notification_id)
    except ValueError as e:
        raise HTTPException(400, "notification_id invalide") from e
    db = SessionLocal()
    try:
        notif = (
            db.query(Notification)
            .filter(Notification.id == nid, Notification.user_id == current_user.id)
            .first()
        )
        if not notif:
            raise HTTPException(404, "Notification introuvable")
        if notif.read_at is None:
            notif.read_at = datetime.now(timezone.utc)
            db.commit()
    finally:
        db.close()


@router.post("/notifications/tout-lire", status_code=204)
async def tout_marquer_lu(current_user: CurrentUser):
    """Marque toutes les notifications non lues comme lues."""
    now = datetime.now(timezone.utc)
    db = SessionLocal()
    try:
        db.query(Notification).filter(
            Notification.user_id == current_user.id,
            Notification.read_at.is_(None),
        ).update({Notification.read_at: now}, synchronize_session=False)
        db.commit()
    finally:
        db.close()


def _serialize(n: Notification) -> dict:
    return {
        "id": str(n.id),
        "ticket_id": str(n.ticket_id),
        "reponse_id": str(n.reponse_id) if n.reponse_id else None,
        "type": n.type,
        "read_at": n.read_at.isoformat() if n.read_at else None,
        "created_at": n.created_at.isoformat() if n.created_at else None,
        "ticket_objet": n.ticket.objet if n.ticket else None,
        "ticket_question": n.ticket.question if n.ticket else None,
    }
