"""Requêtes SQL privées du tableau de bord."""

from datetime import datetime, timedelta

from sqlalchemy import Date, cast, extract, func, or_

from app.models.reponse import Reponse
from app.models.ticket import Ticket


def _count_nouveaux(db, start: datetime, end: datetime, domain_filters: list, reponse_validee_exists) -> int:
    return (
        db.query(func.count(Ticket.id))
        .filter(
            Ticket.created_at >= start,
            Ticket.created_at < end,
            Ticket.closed_at.is_(None),
            ~reponse_validee_exists,
            *domain_filters,
        )
        .scalar()
        or 0
    )


def _count_en_cours(db, start: datetime, end: datetime, domain_filters: list, reponse_validee_exists) -> int:
    return (
        db.query(func.count(Ticket.id))
        .filter(
            Ticket.created_at >= start,
            Ticket.created_at < end,
            Ticket.closed_at.is_(None),
            reponse_validee_exists,
            *domain_filters,
        )
        .scalar()
        or 0
    )


def _count_tickets_closed(db, start: datetime, end: datetime, domain_filters: list) -> int:
    return (
        db.query(func.count(Ticket.id))
        .filter(Ticket.closed_at >= start, Ticket.closed_at < end, *domain_filters)
        .scalar()
        or 0
    )


def _count_repondu_canonique(db, start: datetime, end: datetime, domain_filters: list) -> int:
    return (
        db.query(func.count(func.distinct(Reponse.ticket_id)))
        .join(Ticket, Reponse.ticket_id == Ticket.id)
        .filter(
            Reponse.source == "CANONIQUE",
            Reponse.created_at >= start,
            Reponse.created_at < end,
            *domain_filters,
        )
        .scalar()
        or 0
    )


def _count_tickets_created(db, start: datetime, end: datetime, domain_filters: list) -> int:
    return (
        db.query(func.count(Ticket.id))
        .filter(
            Ticket.created_at >= start,
            Ticket.created_at < end,
            *domain_filters,
        )
        .scalar()
        or 0
    )


def _avg_closure_time(db, start: datetime, end: datetime, domain_filters: list) -> int:
    result = (
        db.query(func.avg(func.extract("epoch", Ticket.closed_at - Ticket.created_at)))
        .filter(
            Ticket.closed_at >= start,
            Ticket.closed_at < end,
            *domain_filters,
        )
        .scalar()
    )
    return round(result) if result else 0


def _avg_first_response_time(db, start: datetime, end: datetime, domain_filters: list) -> int:
    first_rep_sq = (
        db.query(Reponse.ticket_id, func.min(Reponse.validated_at).label("first_at"))
        .filter(
            Reponse.canonique.is_(False),
            Reponse.statut.in_(["VALIDÉE", "CORRIGÉE"]),
        )
        .group_by(Reponse.ticket_id)
        .subquery()
    )
    result = (
        db.query(func.avg(func.extract("epoch", first_rep_sq.c.first_at - Ticket.created_at)))
        .join(first_rep_sq, Ticket.id == first_rep_sq.c.ticket_id)
        .filter(
            Ticket.created_at >= start,
            Ticket.created_at < end,
            *domain_filters,
        )
        .scalar()
    )
    return round(result) if result else 0


def _build_graphiques_annee(db, curr_start, curr_end, today, domain_filters, reponse_domain_joins):
    tickets_rows = (
        db.query(
            extract("year", Ticket.created_at).label("yr"),
            extract("month", Ticket.created_at).label("mo"),
            func.count(Ticket.id),
        )
        .filter(Ticket.created_at >= curr_start, Ticket.created_at < curr_end, *domain_filters)
        .group_by("yr", "mo")
        .all()
    )
    tickets_month_dict = {(int(r.yr), int(r.mo)): r[2] for r in tickets_rows}

    traitement_rows = (
        db.query(
            extract("year", Reponse.created_at).label("yr"),
            extract("month", Reponse.created_at).label("mo"),
            func.count(func.distinct(Reponse.ticket_id)),
        )
        .filter(
            Reponse.created_at >= curr_start,
            Reponse.created_at < curr_end,
            or_(Reponse.statut.in_(["VALIDÉE", "CORRIGÉE"]), Reponse.canonique.is_(True)),
            *reponse_domain_joins,
        )
        .group_by("yr", "mo")
        .all()
    )
    traitement_month_dict = {(int(r.yr), int(r.mo)): r[2] for r in traitement_rows}

    year = today.year
    tickets_par_jour = [
        {"date": f"{year}-{m:02d}-01", "count": tickets_month_dict.get((year, m), 0)} for m in range(1, 13)
    ]
    traitement_par_jour = [
        {"date": f"{year}-{m:02d}-01", "count": traitement_month_dict.get((year, m), 0)} for m in range(1, 13)
    ]
    return tickets_par_jour, traitement_par_jour


def _build_graphiques_jours(db, curr_start, curr_end, domain_filters, reponse_domain_joins):
    daily_rows = (
        db.query(cast(Ticket.created_at, Date), func.count(Ticket.id))
        .filter(Ticket.created_at >= curr_start, Ticket.created_at < curr_end, *domain_filters)
        .group_by(cast(Ticket.created_at, Date))
        .all()
    )
    daily_dict = {str(d): c for d, c in daily_rows}

    traitement_rows = (
        db.query(cast(Reponse.created_at, Date), func.count(func.distinct(Reponse.ticket_id)))
        .filter(
            Reponse.created_at >= curr_start,
            Reponse.created_at < curr_end,
            or_(Reponse.statut.in_(["VALIDÉE", "CORRIGÉE"]), Reponse.canonique.is_(True)),
            *reponse_domain_joins,
        )
        .group_by(cast(Reponse.created_at, Date))
        .all()
    )
    traitement_dict = {str(d): c for d, c in traitement_rows}

    nb_days = (curr_end.date() - curr_start.date()).days
    dates = [str(curr_start.date() + timedelta(days=i)) for i in range(nb_days)]
    tickets_par_jour = [{"date": d, "count": daily_dict.get(d, 0)} for d in dates]
    traitement_par_jour = [{"date": d, "count": traitement_dict.get(d, 0)} for d in dates]
    return tickets_par_jour, traitement_par_jour
