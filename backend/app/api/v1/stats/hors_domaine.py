from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func

from app.api.v1.stats._helpers import _build_domain_filters, _get_period_bounds
from app.core.security import CurrentUser
from app.database import SessionLocal
from app.models.reponse import Reponse
from app.models.ticket import Ticket

router = APIRouter()


@router.get("/hors-domaine")
def get_hors_domaine(
    current_user: CurrentUser,
    periode: str = Query(default="mois", pattern="^(semaine|mois|annee)$"),
):
    now = datetime.now(timezone.utc)
    curr_start, curr_end, _, _ = _get_period_bounds(periode, now)

    db = SessionLocal()
    try:
        domain_filters, _ = _build_domain_filters(current_user, None)

        count_rows = (
            db.query(Ticket.domaine, func.count(func.distinct(Reponse.ticket_id)))
            .join(Reponse, Reponse.ticket_id == Ticket.id)
            .filter(
                Reponse.source == "HORS_DOMAINE",
                Reponse.created_at >= curr_start,
                Reponse.created_at < curr_end,
                Ticket.masque_angles_morts.is_(False),
                *domain_filters,
            )
            .group_by(Ticket.domaine)
            .order_by(func.count(func.distinct(Reponse.ticket_id)).desc())
            .all()
        )

        result = []
        for dom, nb in count_rows:
            question_rows = (
                db.query(Ticket.id, Ticket.objet, Ticket.question, Ticket.created_at)
                .join(Reponse, Reponse.ticket_id == Ticket.id)
                .filter(
                    Reponse.source == "HORS_DOMAINE",
                    Ticket.domaine == dom,
                    Ticket.masque_angles_morts.is_(False),
                    Reponse.created_at >= curr_start,
                    Reponse.created_at < curr_end,
                )
                .distinct()
                .order_by(Ticket.created_at.desc())
                .limit(50)
                .all()
            )
            result.append(
                {
                    "domaine": dom,
                    "nb_tickets": nb,
                    "questions": [
                        {
                            "id": str(r.id),
                            "objet": r.objet,
                            "question": r.question,
                            "created_at": r.created_at.isoformat() if r.created_at else None,
                        }
                        for r in question_rows
                    ],
                }
            )

        return result
    finally:
        db.close()


@router.delete("/hors-domaine/{ticket_id}", status_code=204)
def masquer_angle_mort(ticket_id: str, current_user: CurrentUser):
    db = SessionLocal()
    try:
        domain_filters, _ = _build_domain_filters(current_user, None)
        ticket = (
            db.query(Ticket)
            .filter(Ticket.id == ticket_id, *domain_filters)
            .first()
        )
        if not ticket:
            raise HTTPException(status_code=404, detail="Ticket introuvable")
        ticket.masque_angles_morts = True
        db.commit()
    finally:
        db.close()
