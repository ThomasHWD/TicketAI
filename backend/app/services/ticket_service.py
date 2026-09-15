import uuid
from datetime import datetime, timedelta, timezone

from app.config import settings
from app.models.ticket import Ticket
from fastapi import HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session


def full_name(user) -> str | None:
    return " ".join(filter(None, [user.prenom, user.nom])) or None if user else None


def lock_info(ticket: Ticket, now: datetime | None = None) -> dict:
    """Sérialise l'état du verrou. Un bail expiré est considéré comme libre."""
    now = now or datetime.now(timezone.utc)
    actif = bool(ticket.locked_by and ticket.lock_expires_at and ticket.lock_expires_at > now)
    return {
        "locked_by": str(ticket.locked_by) if actif else None,
        "locked_by_email": ticket.locker.email if actif and ticket.locker else None,
        "lock_expires_at": ticket.lock_expires_at.isoformat() if actif else None,
    }


def serialize_ticket(ticket: Ticket) -> dict:
    return {
        "id": str(ticket.id),
        "question": ticket.question,
        "objet": ticket.objet,
        "domaine": ticket.domaine,
        "statut_ticket": ticket.statut_ticket,
        "statut_job": ticket.statut_job,
        "user_id": str(ticket.user_id) if ticket.user_id else None,
        "user_email": ticket.user.email if ticket.user else None,
        "user_nom_complet": full_name(ticket.user),
        "user_departement": ticket.user.departement if ticket.user else None,
        "user_titre": ticket.user.titre if ticket.user else None,
        "user_telephone": ticket.user.telephone if ticket.user else None,
        "user_localisation": ticket.user.localisation if ticket.user else None,
        "canonique": ticket.canonique,
        "created_at": ticket.created_at.isoformat() if ticket.created_at else None,
        "closed_at": ticket.closed_at.isoformat() if ticket.closed_at else None,
        "validated_at": ticket.validated_at.isoformat() if ticket.validated_at else None,
        "note_qualite": ticket.note_qualite,
        "note_delai": ticket.note_delai,
        **lock_info(ticket),
        "assigned_to": str(ticket.assigned_to) if ticket.assigned_to else None,
        "assigned_to_email": ticket.assignee.email if ticket.assignee else None,
        "assigned_to_nom_complet": full_name(ticket.assignee),
        "reponse_source": next(
            (
                r.source
                for r in sorted(ticket.reponses, key=lambda r: r.created_at or 0, reverse=True)
                if not r.obsolete
            ),
            None,
        ),
        "reroute_source_domaine": ticket.reroute_source_domaine,
    }


def acquire_lock(db: Session, tid: uuid.UUID, validator_id: uuid.UUID) -> Ticket | None:
    """Acquiert/prolonge le bail de façon atomique (UPDATE conditionnel).

    Réussit uniquement si le ticket est libre, déjà détenu par ce validateur,
    ou si le bail précédent a expiré. Renvoie le ticket si acquis, sinon None.
    """
    now = datetime.now(timezone.utc)
    expiry = now + timedelta(seconds=settings.lock_ttl_seconds)
    rows = (
        db.query(Ticket)
        .filter(
            Ticket.id == tid,
            or_(
                Ticket.locked_by.is_(None),
                Ticket.locked_by == validator_id,
                Ticket.lock_expires_at < now,
            ),
        )
        .update(
            {
                Ticket.locked_by: validator_id,
                Ticket.locked_at: now,
                Ticket.lock_expires_at: expiry,
            },
            synchronize_session=False,
        )
    )
    db.commit()
    if not rows:
        return None
    return db.query(Ticket).filter(Ticket.id == tid).first()


def parse_ticket_id(ticket_id: str) -> uuid.UUID:
    try:
        return uuid.UUID(ticket_id)
    except ValueError as e:
        raise HTTPException(400, "ticket_id invalide") from e
