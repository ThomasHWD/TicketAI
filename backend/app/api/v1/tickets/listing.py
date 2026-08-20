import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import and_, or_
from sqlalchemy.orm import joinedload, selectinload

from app.api.v1.stats._helpers import _get_period_bounds
from app.core.permissions import user_domaines
from app.core.security import BackofficeUser, CurrentUser
from app.database import SessionLocal
from app.models.groupe import Groupe
from app.models.reponse import Reponse as ReponseModel
from app.models.ticket import Ticket
from app.services.ticket_service import serialize_ticket

router = APIRouter()


@router.get("/tickets")
async def liste_tickets(
    current_user: CurrentUser,
    page: int = 1,
    limit: int = 10,
    domaine: str | None = None,
    domaines: str | None = None,
    statut: str | None = None,
    user_id: str | None = None,
    closed: bool | None = None,
    search: str | None = None,
    disponibles: bool | None = None,
    note_max: int | None = None,
    periode: str | None = Query(default=None, pattern="^(semaine|mois|annee)$"),
):
    db = SessionLocal()
    try:
        query = db.query(Ticket).options(selectinload(Ticket.reponses))

        if current_user.groupes:
            own_request = False
            if user_id:
                try:
                    if uuid.UUID(user_id) == current_user.id:
                        own_request = True
                except ValueError:
                    pass
            if not own_request:
                allowed = user_domaines(current_user)
                if domaines:
                    requested = {d.strip().upper() for d in domaines.split(",") if d.strip()}
                    allowed = allowed & requested
                elif domaine:
                    requested_single = domaine.upper()
                    if requested_single not in allowed:
                        return {"total": 0, "page": page, "limit": limit, "items": []}
                    allowed = {requested_single}
                query = query.filter(Ticket.domaine.in_(allowed))
        else:
            query = query.filter(Ticket.user_id == current_user.id)

        if disponibles:
            query = query.filter(
                or_(
                    Ticket.assigned_to.is_(None),
                    Ticket.assigned_to == current_user.id,
                )
            )
        if statut:
            query = query.filter(Ticket.statut_ticket == statut.upper())
        if closed is True:
            query = query.filter(Ticket.closed_at.isnot(None))
        elif closed is False:
            query = query.filter(Ticket.closed_at.is_(None))
        if user_id:
            try:
                query = query.filter(Ticket.user_id == uuid.UUID(user_id))
            except ValueError as e:
                raise HTTPException(400, "user_id invalide") from e
        if search:
            try:
                tid = uuid.UUID(search)
                query = query.filter(Ticket.id == tid)
            except ValueError:
                pattern = f"%{search}%"
                query = query.filter(
                    or_(
                        Ticket.objet.ilike(pattern),
                        Ticket.question.ilike(pattern),
                    )
                )
        if note_max is not None:
            query = query.filter(
                or_(
                    and_(Ticket.note_qualite.isnot(None), Ticket.note_qualite <= note_max),
                    and_(Ticket.note_delai.isnot(None), Ticket.note_delai <= note_max),
                )
            )
        if periode is not None:
            curr_start, curr_end, _, _ = _get_period_bounds(periode, datetime.now(timezone.utc))
            query = query.filter(Ticket.closed_at >= curr_start, Ticket.closed_at < curr_end)
        total = query.count()
        tickets = query.order_by(Ticket.created_at.desc()).offset((page - 1) * limit).limit(limit).all()
        return {
            "total": total,
            "page": page,
            "limit": limit,
            "items": [serialize_ticket(t) for t in tickets],
        }
    finally:
        db.close()


@router.get("/tickets/mes-assignations")
async def mes_assignations(current_user: CurrentUser):
    """Tickets ouverts assignés à l'utilisateur courant."""
    db = SessionLocal()
    try:
        tickets = (
            db.query(Ticket)
            .options(selectinload(Ticket.reponses))
            .filter(Ticket.assigned_to == current_user.id, Ticket.closed_at.is_(None))
            .order_by(Ticket.created_at.desc())
            .all()
        )
        return [serialize_ticket(t) for t in tickets]
    finally:
        db.close()


@router.get("/tickets/domaines/{domaine}/validateurs")
async def validateurs_par_domaine(domaine: str, _: BackofficeUser):
    """Liste les membres du groupe pour un domaine donné."""
    db = SessionLocal()
    try:
        groupe = db.query(Groupe).options(joinedload(Groupe.membres)).filter(Groupe.domaine == domaine.upper()).first()
        if not groupe:
            return []
        return [{"id": str(u.id), "email": u.email, "prenom": u.prenom, "nom": u.nom} for u in groupe.membres]
    finally:
        db.close()


@router.get("/tickets/participated")
async def tickets_avec_participation(
    current_user: BackofficeUser,
    page: int = 1,
    limit: int = 10,
):
    db = SessionLocal()
    try:
        base_query = (
            db.query(Ticket)
            .join(ReponseModel, ReponseModel.ticket_id == Ticket.id)
            .filter(ReponseModel.validator_id == current_user.id)
            .distinct()
        )
        total = base_query.count()
        tickets = base_query.order_by(Ticket.created_at.desc()).offset((page - 1) * limit).limit(limit).all()
        return {
            "total": total,
            "page": page,
            "limit": limit,
            "items": [serialize_ticket(t) for t in tickets],
        }
    finally:
        db.close()
