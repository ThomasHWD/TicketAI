import asyncio
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import and_, exists, or_
from sqlalchemy.orm import joinedload, selectinload

from app.api.v1.stats._helpers import _get_period_bounds
from app.core.permissions import check_domain_write, check_ticket_read, user_domaines
from app.core.security import BackofficeUser, CurrentUser
from app.database import SessionLocal
from app.models.groupe import Groupe
from app.models.groupe import user_groups as ug_table
from app.models.reponse import Reponse as ReponseModel
from app.models.ticket import Ticket
from app.models.ticket_event import TicketEvent
from app.models.user import User
from app.schemas.ticket import AssignerRequest
from app.services.broadcast import broadcast_async
from app.services.ticket_service import acquire_lock, full_name, lock_info, parse_ticket_id, serialize_ticket

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

        if current_user.role == "ADMIN":
            pass
        elif current_user.groupes:
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


@router.post("/tickets/{ticket_id}/assigner")
async def assigner_ticket(ticket_id: str, payload: AssignerRequest, current_user: BackofficeUser):
    """Assigne le ticket à un validateur du même domaine."""
    tid = parse_ticket_id(ticket_id)
    db = SessionLocal()
    try:
        ticket = db.query(Ticket).filter(Ticket.id == tid).first()
        if not ticket:
            raise HTTPException(404, "Ticket introuvable")
        check_domain_write(ticket.domaine, current_user)
        is_member = db.query(
            exists()
            .where(Groupe.domaine == ticket.domaine)
            .where(ug_table.c.groupe_id == Groupe.id)
            .where(ug_table.c.user_id == payload.assignee_id)
        ).scalar()
        if not is_member:
            raise HTTPException(422, "L'assigné n'appartient pas au domaine du ticket")
        domaine = ticket.domaine
        ticket.assigned_to = payload.assignee_id
        ticket.locked_by = None
        ticket.locked_at = None
        ticket.lock_expires_at = None
        assignee = db.query(User).filter(User.id == payload.assignee_id).first()
        db.add(
            TicketEvent(
                ticket_id=tid,
                type="ASSIGNE",
                actor_id=current_user.id,
                actor_email=current_user.email,
                actor_nom_complet=full_name(current_user),
                meta={
                    "assignee_id": str(payload.assignee_id),
                    "assignee_email": assignee.email if assignee else None,
                    "assignee_nom": full_name(assignee) if assignee else None,
                },
            )
        )
        db.commit()
        result = serialize_ticket(ticket)
    finally:
        db.close()
    await asyncio.gather(
        broadcast_async(f"sse:domain:{domaine}", "ticket_unlocked", {"ticket_id": ticket_id}),
        broadcast_async(f"sse:domain:{domaine}", "ticket_assigned", {"ticket_id": ticket_id, "domaine": domaine}),
        broadcast_async(
            f"sse:user:{payload.assignee_id}", "ticket_assigned", {"ticket_id": ticket_id, "domaine": domaine}
        ),
    )
    return result


@router.post("/tickets/{ticket_id}/desassigner")
async def desassigner_ticket(ticket_id: str, current_user: BackofficeUser):
    """Remet le ticket dans le pot commun (supprime l'assignation)."""
    tid = parse_ticket_id(ticket_id)
    db = SessionLocal()
    try:
        ticket = db.query(Ticket).filter(Ticket.id == tid).first()
        if not ticket:
            raise HTTPException(404, "Ticket introuvable")
        check_domain_write(ticket.domaine, current_user)
        domaine = ticket.domaine
        ticket.assigned_to = None
        db.add(
            TicketEvent(
                ticket_id=tid,
                type="DESASSIGNE",
                actor_id=current_user.id,
                actor_email=current_user.email,
                actor_nom_complet=full_name(current_user),
                meta={},
            )
        )
        db.commit()
        result = serialize_ticket(ticket)
    finally:
        db.close()
    await broadcast_async(f"sse:domain:{domaine}", "ticket_unassigned", {"ticket_id": ticket_id, "domaine": domaine})
    return result


@router.get("/tickets/{ticket_id}/reponses")
async def reponses_par_ticket(ticket_id: str, current_user: CurrentUser):
    db = SessionLocal()
    try:
        try:
            tid = uuid.UUID(ticket_id)
        except ValueError as e:
            raise HTTPException(400, "ticket_id invalide") from e
        ticket = db.query(Ticket).filter(Ticket.id == tid).first()
        if not ticket:
            raise HTTPException(404, "Ticket introuvable")
        check_ticket_read(ticket, current_user)
        reponses = (
            db.query(ReponseModel)
            .filter(ReponseModel.ticket_id == tid, ReponseModel.obsolete.is_(False))
            .order_by(ReponseModel.created_at.asc())
            .all()
        )
        return [
            {
                "id": str(r.id),
                "ticket_id": str(r.ticket_id),
                "contenu": r.contenu,
                "contenu_corrige": r.contenu_corrige,
                "question_suivi": r.question_suivi,
                "statut": r.statut,
                "source": r.source,
                "nb_validations": r.nb_validations,
                "canonique": r.canonique,
                "score_similarite": r.score_similarite,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "validator_email": r.validator.email if r.validator else None,
                "validator_nom_complet": full_name(r.validator) or (r.validator.email if r.validator else None),
            }
            for r in reponses
        ]
    finally:
        db.close()


@router.get("/tickets/{ticket_id}/workflow")
async def get_ticket_workflow(ticket_id: str, current_user: CurrentUser):
    """Retourne la timeline complète du ticket, triée chronologiquement."""
    db = SessionLocal()
    try:
        tid = parse_ticket_id(ticket_id)
        ticket = db.query(Ticket).filter(Ticket.id == tid).first()
        if not ticket:
            raise HTTPException(404, "Ticket introuvable")
        check_ticket_read(ticket, current_user)

        reponses = (
            db.query(ReponseModel).filter(ReponseModel.ticket_id == tid).order_by(ReponseModel.created_at.asc()).all()
        )
        ticket_events = (
            db.query(TicketEvent).filter(TicketEvent.ticket_id == tid).order_by(TicketEvent.created_at.asc()).all()
        )

        _TYPE_ORDER = {
            "CREE": 0,
            "SUIVI": 1,
            "REPONSE_GENEREE": 2,
            "ASSIGNE": 3,
            "DESASSIGNE": 3,
            "VALIDE": 4,
            "CORRIGE": 4,
            "REJETE": 4,
            "CLOTURE": 5,
        }

        events: list[dict] = []

        events.append(
            {
                "type": "CREE",
                "at": ticket.created_at.isoformat() if ticket.created_at else None,
                "actor_email": ticket.user.email if ticket.user else None,
                "actor_nom_complet": full_name(ticket.user),
                "meta": {"domaine": ticket.domaine},
            }
        )

        type_map = {"VALIDÉE": "VALIDE", "CORRIGÉE": "CORRIGE", "REJETÉE": "REJETE"}
        for reponse in reponses:
            ts = reponse.created_at.isoformat() if reponse.created_at else None
            if reponse.question_suivi:
                events.append(
                    {
                        "type": "SUIVI",
                        "at": ts,
                        "actor_email": None,
                        "actor_nom_complet": None,
                        "meta": {"texte": reponse.question_suivi},
                    }
                )
            events.append(
                {
                    "type": "REPONSE_GENEREE",
                    "at": ts,
                    "actor_email": None,
                    "actor_nom_complet": None,
                    "meta": {"source": reponse.source},
                }
            )
            if reponse.validated_at and reponse.statut in type_map:
                events.append(
                    {
                        "type": type_map[reponse.statut],
                        "at": reponse.validated_at.isoformat(),
                        "actor_email": reponse.validator.email if reponse.validator else None,
                        "actor_nom_complet": full_name(reponse.validator),
                        "meta": {},
                    }
                )

        for evt in ticket_events:
            events.append(
                {
                    "type": evt.type,
                    "at": evt.created_at.isoformat() if evt.created_at else None,
                    "actor_email": evt.actor_email,
                    "actor_nom_complet": evt.actor_nom_complet,
                    "meta": evt.meta or {},
                }
            )

        if ticket.closed_at:
            events.append(
                {
                    "type": "CLOTURE",
                    "at": ticket.closed_at.isoformat(),
                    "actor_email": None,
                    "actor_nom_complet": None,
                    "meta": {},
                }
            )

        events.sort(key=lambda e: (e["at"] or "", _TYPE_ORDER.get(e["type"], 6)))
        return events
    finally:
        db.close()


@router.get("/tickets/{ticket_id}")
async def get_ticket(ticket_id: str, current_user: CurrentUser):
    db = SessionLocal()
    try:
        try:
            tid = uuid.UUID(ticket_id)
        except ValueError as e:
            raise HTTPException(400, "ticket_id invalide") from e
        ticket = db.query(Ticket).filter(Ticket.id == tid).first()
        if not ticket:
            raise HTTPException(404, "Ticket introuvable")
        check_ticket_read(ticket, current_user)
        return serialize_ticket(ticket)
    finally:
        db.close()


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
async def heartbeat_ticket(ticket_id: str, current_user: CurrentUser):
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
