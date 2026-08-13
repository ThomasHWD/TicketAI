from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Query
from sqlalchemy import Date, cast, exists, extract, func, or_

from app.api.v1.stats._helpers import (
    _avg_satisfaction,
    _get_period_bounds,
    _variation,
    _variation_taux,
    _variation_temps,
)
from app.core.security import CurrentUser
from app.database import SessionLocal
from app.models.reponse import Reponse
from app.models.ticket import Ticket

router = APIRouter()


def _build_domain_filters(current_user, domaine: str | None) -> tuple[list, list]:
    """Retourne (domain_filters, reponse_domain_joins) selon l'utilisateur et le domaine demandé."""
    if domaine:
        domaine = domaine.upper()
        return (
            [Ticket.domaine == domaine],
            [Reponse.ticket.has(Ticket.domaine == domaine)],
        )
    if current_user.role == "ADMIN":
        return [], []
    user_domaines = [g.domaine for g in current_user.groupes]
    if user_domaines:
        return (
            [Ticket.domaine.in_(user_domaines)],
            [Reponse.ticket.has(Ticket.domaine.in_(user_domaines))],
        )
    return [Ticket.id.is_(None)], [Reponse.id.is_(None)]


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
            Ticket.canonique.is_(False),
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


@router.get("/dashboard")
def get_dashboard_stats(
    current_user: CurrentUser,
    periode: str = Query(default="semaine", pattern="^(semaine|mois|annee)$"),
    domaine: str | None = Query(default=None),
):
    now = datetime.now(timezone.utc)
    curr_start, curr_end, prev_start, prev_end = _get_period_bounds(periode, now)

    db = SessionLocal()
    try:
        domain_filters, reponse_domain_joins = _build_domain_filters(current_user, domaine)

        # Prédicat : ticket ayant au moins une réponse validée/canonique
        reponse_validee_exists = exists().where(
            Reponse.ticket_id == Ticket.id,
            or_(
                Reponse.statut.in_(["VALIDÉE", "CORRIGÉE"]),
                Reponse.canonique.is_(True),
            ),
        )

        # ── Stat cartes ──────────────────────────────────────────────────────────
        stats_cartes = {
            "nouveaux": _variation(
                _count_nouveaux(db, curr_start, curr_end, domain_filters, reponse_validee_exists),
                _count_nouveaux(db, prev_start, prev_end, domain_filters, reponse_validee_exists),
            ),
            "en_cours": _variation(
                _count_en_cours(db, curr_start, curr_end, domain_filters, reponse_validee_exists),
                _count_en_cours(db, prev_start, prev_end, domain_filters, reponse_validee_exists),
            ),
            "tickets_clotures": _variation(
                _count_tickets_closed(db, curr_start, curr_end, domain_filters),
                _count_tickets_closed(db, prev_start, prev_end, domain_filters),
            ),
            "repondu_canonique": _variation_taux(
                _count_repondu_canonique(db, curr_start, curr_end, domain_filters),
                _count_tickets_created(db, curr_start, curr_end, domain_filters),
                _count_repondu_canonique(db, prev_start, prev_end, domain_filters),
                _count_tickets_created(db, prev_start, prev_end, domain_filters),
            ),
            "temps_premiere_reponse": _variation_temps(
                _avg_first_response_time(db, curr_start, curr_end, domain_filters),
                _avg_first_response_time(db, prev_start, prev_end, domain_filters),
            ),
            "temps_cloture": _variation_temps(
                _avg_closure_time(db, curr_start, curr_end, domain_filters),
                _avg_closure_time(db, prev_start, prev_end, domain_filters),
            ),
        }

        # ── Répartition statuts ──────────────────────────────────────────────────
        nb_nouveau_rep = _count_nouveaux(db, curr_start, curr_end, domain_filters, reponse_validee_exists)
        nb_en_cours_rep = _count_en_cours(db, curr_start, curr_end, domain_filters, reponse_validee_exists)
        nb_clotures_rep = _count_tickets_closed(db, curr_start, curr_end, domain_filters)
        total_rep = (nb_nouveau_rep + nb_en_cours_rep + nb_clotures_rep) or 1
        repartition_statuts = [
            {"statut": "NOUVEAU", "count": nb_nouveau_rep, "pct": round(nb_nouveau_rep / total_rep * 100, 1)},
            {"statut": "EN COURS", "count": nb_en_cours_rep, "pct": round(nb_en_cours_rep / total_rep * 100, 1)},
            {"statut": "CLOTURÉ", "count": nb_clotures_rep, "pct": round(nb_clotures_rep / total_rep * 100, 1)},
        ]

        # ── Répartition branches ─────────────────────────────────────────────────
        branch_rows = (
            db.query(Reponse.source, func.count(func.distinct(Reponse.ticket_id)))
            .join(Ticket, Reponse.ticket_id == Ticket.id)
            .filter(
                Reponse.source.in_(["CANONIQUE", "SUGGESTION", "LLM"]),
                Ticket.created_at >= curr_start,
                Ticket.created_at < curr_end,
                *domain_filters,
            )
            .group_by(Reponse.source)
            .all()
        )
        branch_counts = dict(branch_rows)
        nb_canonique = branch_counts.get("CANONIQUE", 0)
        nb_suggestion = branch_counts.get("SUGGESTION", 0)
        nb_llm = branch_counts.get("LLM", 0)
        total_branches = (nb_canonique + nb_suggestion + nb_llm) or 1
        repartition_branches = [
            {"branche": "CANONIQUE", "count": nb_canonique, "pct": round(nb_canonique / total_branches * 100, 1)},
            {"branche": "SUGGESTION", "count": nb_suggestion, "pct": round(nb_suggestion / total_branches * 100, 1)},
            {"branche": "LLM", "count": nb_llm, "pct": round(nb_llm / total_branches * 100, 1)},
        ]

        # ── Graphiques ───────────────────────────────────────────────────────────
        today = now.date()
        if periode == "annee":
            tickets_par_jour, traitement_par_jour = _build_graphiques_annee(
                db, curr_start, curr_end, today, domain_filters, reponse_domain_joins
            )
        else:
            tickets_par_jour, traitement_par_jour = _build_graphiques_jours(
                db, curr_start, curr_end, domain_filters, reponse_domain_joins
            )

        # ── Derniers tickets ─────────────────────────────────────────────────────
        derniers_tickets_rows = (
            db.query(Ticket)
            .filter(Ticket.created_at >= curr_start, Ticket.created_at < curr_end, *domain_filters)
            .order_by(Ticket.created_at.desc())
            .limit(5)
            .all()
        )
        derniers_tickets = [
            {
                "id": str(t.id),
                "objet": t.objet or t.question[:80],
                "domaine": t.domaine,
                "statut_ticket": t.statut_ticket,
                "statut_job": t.statut_job,
                "created_at": t.created_at.isoformat() if t.created_at else None,
            }
            for t in derniers_tickets_rows
        ]

        return {
            "periode": periode,
            "stats_cartes": stats_cartes,
            "repartition_statuts": repartition_statuts,
            "repartition_branches": repartition_branches,
            "tickets_par_jour": tickets_par_jour,
            "traitement_par_jour": traitement_par_jour,
            "derniers_tickets": derniers_tickets,
            "satisfaction": _avg_satisfaction(db, curr_start, curr_end, domain_filters),
        }
    finally:
        db.close()
