import uuid

from fastapi import APIRouter, HTTPException

from app.core.permissions import check_ticket_read
from app.core.security import CurrentUser
from app.database import SessionLocal
from app.models.reponse import Reponse as ReponseModel
from app.models.ticket import Ticket
from app.models.ticket_event import TicketEvent
from app.services.ticket_service import full_name, parse_ticket_id, serialize_ticket

router = APIRouter()


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
                "raison_rejet": r.raison_rejet,
                "tag": r.tag,
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
                        "meta": {"raison": reponse.raison_rejet} if reponse.statut == "REJETÉE"\
                            and reponse.raison_rejet else {},
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
