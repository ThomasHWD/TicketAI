from fastapi import APIRouter, HTTPException

from app.core.permissions import check_domain_write
from app.core.security import BackofficeUser, CurrentUser
from app.database import SessionLocal
from app.models.ticket import Ticket
from app.services.broadcast import broadcast_async
from app.services.ticket_service import acquire_lock, lock_info, parse_ticket_id

router = APIRouter()


@router.post("/tickets/{ticket_id}/lock")
async def verrouiller_ticket(ticket_id: str, current_user: BackofficeUser):
    """Prend (ou prolonge) le verrou du ticket pour le validateur courant."""
    tid = parse_ticket_id(ticket_id)
    db = SessionLocal()
    try:
        existing = db.query(Ticket).filter(Ticket.id == tid).first()
        if not existing:
            raise HTTPException(404, "Ticket introuvable")
        check_domain_write(existing.domaine, current_user)
        domaine = existing.domaine

        if existing.assigned_to and existing.assigned_to != current_user.id:
            raise HTTPException(
                409,
                {
                    "message": "Ce ticket est assigné à un autre validateur.",
                    "locked_by_email": existing.assignee.email if existing.assignee else None,
                    "lock_expires_at": None,
                    "is_assigned": True,
                },
            )

        ticket = acquire_lock(db, tid, current_user.id)
        if ticket is None:
            ticket = db.query(Ticket).filter(Ticket.id == tid).first()
            raise HTTPException(
                409,
                {
                    "message": "Ticket verrouillé par un autre validateur.",
                    **lock_info(ticket),
                },
            )
        result = {"ticket_id": ticket_id, "is_mine": True, **lock_info(ticket)}
    finally:
        db.close()
    await broadcast_async(
        f"sse:domain:{domaine}",
        "ticket_locked",
        {"ticket_id": ticket_id, "locked_by_email": current_user.email},
    )
    return result


@router.post("/tickets/{ticket_id}/heartbeat")
async def heartbeat_ticket(ticket_id: str, current_user: BackofficeUser):
    """Prolonge le bail tant que le validateur garde le ticket ouvert."""
    tid = parse_ticket_id(ticket_id)
    db = SessionLocal()
    try:
        ticket = acquire_lock(db, tid, current_user.id)
        if ticket is None:
            ticket = db.query(Ticket).filter(Ticket.id == tid).first()
            if not ticket:
                raise HTTPException(404, "Ticket introuvable")
            raise HTTPException(
                409,
                {
                    "message": "Verrou perdu au profit d'un autre validateur.",
                    **lock_info(ticket),
                },
            )
        return {"ticket_id": ticket_id, "is_mine": True, **lock_info(ticket)}
    finally:
        db.close()


@router.post("/tickets/{ticket_id}/unlock", status_code=204)
async def deverrouiller_ticket(ticket_id: str, current_user: CurrentUser):
    """Libère le verrou (uniquement si détenu par ce validateur). Idempotent."""
    tid = parse_ticket_id(ticket_id)
    db = SessionLocal()
    domaine = None
    try:
        ticket = db.query(Ticket).filter(Ticket.id == tid).first()
        if ticket:
            domaine = ticket.domaine
        db.query(Ticket).filter(
            Ticket.id == tid,
            Ticket.locked_by == current_user.id,
        ).update(
            {
                Ticket.locked_by: None,
                Ticket.locked_at: None,
                Ticket.lock_expires_at: None,
            },
            synchronize_session=False,
        )
        db.commit()
    finally:
        db.close()
    if domaine:
        await broadcast_async(f"sse:domain:{domaine}", "ticket_unlocked", {"ticket_id": ticket_id})
