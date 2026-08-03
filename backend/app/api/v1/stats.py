from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Query
from sqlalchemy import cast, Date, exists, extract, func, or_

from app.core.security import CurrentUser
from app.database import SessionLocal
from app.models.reponse import Reponse
from app.models.ticket import Ticket

router = APIRouter()


def _get_period_bounds(periode: str, now: datetime) -> tuple[datetime, datetime, datetime, datetime]:
    """Retourne (curr_start, curr_end, prev_start, prev_end) en UTC."""
    today = now.date()
    if periode == "semaine":
        curr_start = today - timedelta(days=today.weekday())
        curr_end = curr_start + timedelta(days=7)
        prev_start = curr_start - timedelta(days=7)
        prev_end = curr_start
    elif periode == "mois":
        curr_start = today.replace(day=1)
        if today.month == 12:
            curr_end = today.replace(year=today.year + 1, month=1, day=1)
        else:
            curr_end = today.replace(month=today.month + 1, day=1)
        if curr_start.month == 1:
            prev_start = curr_start.replace(year=curr_start.year - 1, month=12)
        else:
            prev_start = curr_start.replace(month=curr_start.month - 1)
        prev_end = curr_start
    else:  # annee
        curr_start = today.replace(month=1, day=1)
        curr_end = today.replace(year=today.year + 1, month=1, day=1)
        prev_start = curr_start.replace(year=curr_start.year - 1)
        prev_end = curr_start

    tz = timezone.utc
    return (
        datetime(curr_start.year, curr_start.month, curr_start.day, tzinfo=tz),
        datetime(curr_end.year, curr_end.month, curr_end.day, tzinfo=tz),
        datetime(prev_start.year, prev_start.month, prev_start.day, tzinfo=tz),
        datetime(prev_end.year, prev_end.month, prev_end.day, tzinfo=tz),
    )


def _variation(curr: int, prev: int) -> dict:
    if prev == 0:
        pct = 100.0 if curr > 0 else 0.0
    else:
        pct = round((curr - prev) / prev * 100, 1)
    return {"valeur": curr, "variation": pct, "hausse": curr >= prev}


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
        # Déterminer les filtres de domaine
        if domaine:
            domaine = domaine.upper()
            domain_filters = [Ticket.domaine == domaine]
            reponse_domain_joins = [Reponse.ticket.has(Ticket.domaine == domaine)]
        elif current_user.role == "ADMIN":
            domain_filters = []
            reponse_domain_joins = []
        else:
            user_domaines = [g.domaine for g in current_user.groupes]
            domain_filters = [Ticket.domaine.in_(user_domaines)] if user_domaines else [Ticket.id.is_(None)]
            reponse_domain_joins = (
                [Reponse.ticket.has(Ticket.domaine.in_(user_domaines))] if user_domaines else [Reponse.id.is_(None)]
            )

        # ── Prédicat : ticket ayant au moins une réponse validée/canonique ────────
        # "Validée" = statut VALIDÉE ou CORRIGÉE, ou réponse canonique (canonique=True)
        reponse_validee_exists = exists().where(
            Reponse.ticket_id == Ticket.id,
            or_(
                Reponse.statut.in_(["VALIDÉE", "CORRIGÉE"]),
                Reponse.canonique.is_(True),
            ),
        )

        # ── Stat cartes ─────────────────────────────────────────────────────────
        # Cycle de vie :
        #   NOUVEAU   → ticket sans aucune réponse validée/canonique (humain n'a pas agi)
        #   EN COURS  → ticket avec au moins une réponse validée/canonique, non clôturé
        #   CLÔTURÉ   → closed_at IS NOT NULL
        #   RÉPONSE CANONIQUE → total courant de tickets avec réponse canonique

        # — Nouveaux tickets : créés dans la période, sans réponse validée/canonique —
        def count_nouveaux(start: datetime, end: datetime) -> int:
            return (
                db.query(func.count(Ticket.id))
                .filter(
                    Ticket.created_at >= start,
                    Ticket.created_at < end,
                    Ticket.closed_at.is_(None),
                    ~reponse_validee_exists,
                    *domain_filters,
                )
                .scalar() or 0
            )

        # — En cours : créés dans la période, avec réponse validée/canonique, non clôturé —
        def count_en_cours(start: datetime, end: datetime) -> int:
            return (
                db.query(func.count(Ticket.id))
                .filter(
                    Ticket.created_at >= start,
                    Ticket.created_at < end,
                    Ticket.closed_at.is_(None),
                    reponse_validee_exists,
                    *domain_filters,
                )
                .scalar() or 0
            )

        # — Clôturés : tickets clôturés dans la période —
        def count_tickets_closed(start: datetime, end: datetime) -> int:
            return (
                db.query(func.count(Ticket.id))
                .filter(Ticket.closed_at >= start, Ticket.closed_at < end, *domain_filters)
                .scalar() or 0
            )

        # — Réponses canoniques : total courant tickets avec réponse canonique —
        reponse_canonique_exists = exists().where(
            Reponse.ticket_id == Ticket.id,
            Reponse.canonique.is_(True),
        )

        def count_canoniques_at(before: datetime | None = None) -> int:
            q = (
                db.query(func.count(Ticket.id))
                .filter(
                    Ticket.closed_at.is_(None),
                    reponse_canonique_exists,
                    *domain_filters,
                )
            )
            if before is not None:
                q = q.filter(Ticket.created_at < before)
            return q.scalar() or 0

        stats_cartes = {
            "en_suggestion": _variation(
                count_nouveaux(curr_start, curr_end),
                count_nouveaux(prev_start, prev_end),
            ),
            "en_cours": _variation(
                count_en_cours(curr_start, curr_end),
                count_en_cours(prev_start, prev_end),
            ),
            "tickets_clotures": _variation(
                count_tickets_closed(curr_start, curr_end),
                count_tickets_closed(prev_start, prev_end),
            ),
            "reponses_canoniques": _variation(
                count_canoniques_at(),
                count_canoniques_at(before=curr_start),
            ),
        }

        # ── Répartition en 3 catégories — filtrée par la période ────────────────
        # NOUVEAU  = créé dans la période, pas de réponse validée/canonique, non clôturé
        # EN COURS = créé dans la période, au moins une réponse validée/canonique, non clôturé
        # CLOTURÉ  = clôturé dans la période

        nb_nouveau_rep = (
            db.query(func.count(Ticket.id))
            .filter(
                Ticket.created_at >= curr_start,
                Ticket.created_at < curr_end,
                Ticket.closed_at.is_(None),
                ~reponse_validee_exists,
                *domain_filters,
            )
            .scalar() or 0
        )
        nb_en_cours_rep = (
            db.query(func.count(Ticket.id))
            .filter(
                Ticket.created_at >= curr_start,
                Ticket.created_at < curr_end,
                Ticket.closed_at.is_(None),
                reponse_validee_exists,
                *domain_filters,
            )
            .scalar() or 0
        )
        nb_clotures_rep = (
            db.query(func.count(Ticket.id))
            .filter(
                Ticket.closed_at >= curr_start,
                Ticket.closed_at < curr_end,
                *domain_filters,
            )
            .scalar() or 0
        )
        total_rep = (nb_nouveau_rep + nb_en_cours_rep + nb_clotures_rep) or 1
        repartition_statuts = [
            {"statut": "NOUVEAU",  "count": nb_nouveau_rep,   "pct": round(nb_nouveau_rep   / total_rep * 100, 1)},
            {"statut": "EN COURS", "count": nb_en_cours_rep,  "pct": round(nb_en_cours_rep  / total_rep * 100, 1)},
            {"statut": "CLOTURÉ",  "count": nb_clotures_rep,  "pct": round(nb_clotures_rep  / total_rep * 100, 1)},
        ]

        today = now.date()

        # ── Graphiques : granularité selon la période ────────────────────────────
        # semaine → 7 points journaliers
        # mois    → 30 points journaliers
        # annee   → 12 points mensuels

        if periode == "annee":
            # Agrégation par mois (12 points)
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
                    extract("year", Reponse.validated_at).label("yr"),
                    extract("month", Reponse.validated_at).label("mo"),
                    func.count(Reponse.id),
                )
                .filter(
                    Reponse.validated_at >= curr_start,
                    Reponse.validated_at < curr_end,
                    Reponse.validated_at.is_not(None),
                    *reponse_domain_joins,
                )
                .group_by("yr", "mo")
                .all()
            )
            traitement_month_dict = {(int(r.yr), int(r.mo)): r[2] for r in traitement_rows}

            year = today.year
            tickets_par_jour = [
                {"date": f"{year}-{m:02d}-01", "count": tickets_month_dict.get((year, m), 0)}
                for m in range(1, 13)
            ]
            traitement_par_jour = [
                {"date": f"{year}-{m:02d}-01", "count": traitement_month_dict.get((year, m), 0)}
                for m in range(1, 13)
            ]
        else:
            nb_days = 7 if periode == "semaine" else 30
            chart_start = now - timedelta(days=nb_days)

            daily_rows = (
                db.query(cast(Ticket.created_at, Date), func.count(Ticket.id))
                .filter(Ticket.created_at >= chart_start, *domain_filters)
                .group_by(cast(Ticket.created_at, Date))
                .all()
            )
            daily_dict = {str(d): c for d, c in daily_rows}
            tickets_par_jour = [
                {"date": str(today - timedelta(days=i)), "count": daily_dict.get(str(today - timedelta(days=i)), 0)}
                for i in range(nb_days - 1, -1, -1)
            ]

            traitement_rows = (
                db.query(cast(Reponse.validated_at, Date), func.count(Reponse.id))
                .filter(
                    Reponse.validated_at >= chart_start,
                    Reponse.validated_at.is_not(None),
                    *reponse_domain_joins,
                )
                .group_by(cast(Reponse.validated_at, Date))
                .all()
            )
            traitement_dict = {str(d): c for d, c in traitement_rows}
            traitement_par_jour = [
                {"date": str(today - timedelta(days=i)), "count": traitement_dict.get(str(today - timedelta(days=i)), 0)}
                for i in range(nb_days - 1, -1, -1)
            ]

        # ── Derniers tickets — filtrés par la période ────────────────────────────
        derniers_tickets_rows = (
            db.query(Ticket)
            .filter(
                Ticket.created_at >= curr_start,
                Ticket.created_at < curr_end,
                *domain_filters,
            )
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
            "tickets_par_jour": tickets_par_jour,
            "traitement_par_jour": traitement_par_jour,
            "derniers_tickets": derniers_tickets,
        }
    finally:
        db.close()
