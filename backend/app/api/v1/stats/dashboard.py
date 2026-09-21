from datetime import datetime, timezone

from fastapi import APIRouter, Query
from sqlalchemy import exists, func, or_

from app.api.v1.stats._helpers import (
    _avg_satisfaction,
    _build_domain_filters,
    _get_period_bounds,
    _variation,
    _variation_taux,
    _variation_temps,
)
from app.api.v1.stats._queries import (
    _avg_closure_time,
    _avg_first_response_time,
    _build_graphiques_annee,
    _build_graphiques_jours,
    _count_en_cours,
    _count_nouveaux,
    _count_repondu_canonique,
    _count_tickets_closed,
    _count_tickets_created,
)
from app.core.security import CurrentUser
from app.database import SessionLocal
from app.models.reponse import Reponse
from app.models.ticket import Ticket

router = APIRouter()


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

        reponse_validee_exists = exists().where(
            Reponse.ticket_id == Ticket.id,
            or_(
                Reponse.statut.in_(["VALIDÉE", "CORRIGÉE"]),
                Reponse.canonique.is_(True),
            ),
        )

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

        nb_nouveau_rep = _count_nouveaux(db, curr_start, curr_end, domain_filters, reponse_validee_exists)
        nb_en_cours_rep = _count_en_cours(db, curr_start, curr_end, domain_filters, reponse_validee_exists)
        nb_clotures_rep = _count_tickets_closed(db, curr_start, curr_end, domain_filters)
        total_rep = (nb_nouveau_rep + nb_en_cours_rep + nb_clotures_rep) or 1
        repartition_statuts = [
            {"statut": "NOUVEAU", "count": nb_nouveau_rep, "pct": round(nb_nouveau_rep / total_rep * 100, 1)},
            {"statut": "EN COURS", "count": nb_en_cours_rep, "pct": round(nb_en_cours_rep / total_rep * 100, 1)},
            {"statut": "CLOTURÉ", "count": nb_clotures_rep, "pct": round(nb_clotures_rep / total_rep * 100, 1)},
        ]

        branch_rows = (
            db.query(Reponse.source, func.count(func.distinct(Reponse.ticket_id)))
            .join(Ticket, Reponse.ticket_id == Ticket.id)
            .filter(
                Reponse.source.in_(["CANONIQUE", "SUGGESTION", "LLM", "HORS_DOMAINE"]),
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
        nb_hors_domaine = branch_counts.get("HORS_DOMAINE", 0)
        total_branches = (nb_canonique + nb_suggestion + nb_llm + nb_hors_domaine) or 1
        repartition_branches = [
            {"branche": "CANONIQUE", "count": nb_canonique, "pct": round(nb_canonique / total_branches * 100, 1)},
            {"branche": "SUGGESTION", "count": nb_suggestion, "pct": round(nb_suggestion / total_branches * 100, 1)},
            {"branche": "LLM", "count": nb_llm, "pct": round(nb_llm / total_branches * 100, 1)},
            {"branche": "HORS_DOMAINE", "count": nb_hors_domaine,
             "pct": round(nb_hors_domaine / total_branches * 100, 1)},
        ]

        today = now.date()
        if periode == "annee":
            tickets_par_jour, traitement_par_jour = _build_graphiques_annee(
                db, curr_start, curr_end, today, domain_filters, reponse_domain_joins
            )
        else:
            tickets_par_jour, traitement_par_jour = _build_graphiques_jours(
                db, curr_start, curr_end, domain_filters, reponse_domain_joins
            )

        derniers_tickets_rows = (
            db.query(Ticket)
            .filter(Ticket.created_at >= curr_start, Ticket.created_at < curr_end, *domain_filters)
            .order_by(Ticket.created_at.desc())
            .limit(5)
            .all()
        )
        ticket_ids = [t.id for t in derniers_tickets_rows]
        source_by_ticket: dict = {}
        if ticket_ids:
            reponse_source_rows = (
                db.query(Reponse.ticket_id, Reponse.source)
                .filter(Reponse.ticket_id.in_(ticket_ids))
                .order_by(Reponse.ticket_id, Reponse.created_at.desc())
                .all()
            )
            for row in reponse_source_rows:
                if row.ticket_id not in source_by_ticket:
                    source_by_ticket[row.ticket_id] = row.source
        derniers_tickets = [
            {
                "id": str(t.id),
                "objet": t.objet or t.question[:80],
                "domaine": t.domaine,
                "statut_ticket": t.statut_ticket,
                "statut_job": t.statut_job,
                "branche": source_by_ticket.get(t.id),
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
