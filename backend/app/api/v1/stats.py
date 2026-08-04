from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import Date, cast, exists, extract, func, or_, select

from app.core.security import CurrentUser
from app.database import SessionLocal
from app.models.document_upload import DocumentUpload
from app.models.groupe import Groupe, user_groups
from app.models.reponse import Reponse
from app.models.ticket import Ticket
from app.models.user import User

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
        # nouveaux         → créés dans la période, sans réponse validée/canonique, non clôturés
        # en_cours         → créés dans la période, avec au moins une réponse validée/canonique, non clôturés
        # tickets_clotures → clôturés dans la période
        # repondu_canonique → ayant eu au moins une réponse canonique dans la période

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

        def count_tickets_closed(start: datetime, end: datetime) -> int:
            return (
                db.query(func.count(Ticket.id))
                .filter(Ticket.closed_at >= start, Ticket.closed_at < end, *domain_filters)
                .scalar() or 0
            )

        def count_repondu_canonique(start: datetime, end: datetime) -> int:
            return (
                db.query(func.count(func.distinct(Reponse.ticket_id)))
                .join(Ticket, Reponse.ticket_id == Ticket.id)
                .filter(
                    Reponse.canonique.is_(True),
                    Reponse.created_at >= start,
                    Reponse.created_at < end,
                    *domain_filters,
                )
                .scalar() or 0
            )

        stats_cartes = {
            "nouveaux": _variation(
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
            "repondu_canonique": _variation(
                count_repondu_canonique(curr_start, curr_end),
                count_repondu_canonique(prev_start, prev_end),
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
                {"date": f"{year}-{m:02d}-01", "count": tickets_month_dict.get((year, m), 0)}
                for m in range(1, 13)
            ]
            traitement_par_jour = [
                {"date": f"{year}-{m:02d}-01", "count": traitement_month_dict.get((year, m), 0)}
                for m in range(1, 13)
            ]
        else:
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
            tickets_par_jour = [
                {"date": d, "count": daily_dict.get(d, 0)}
                for d in dates
            ]
            traitement_par_jour = [
                {"date": d, "count": traitement_dict.get(d, 0)}
                for d in dates
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


@router.get("/groupe/{groupe_id}/membres")
def get_groupe_membres_stats(
    groupe_id: UUID,
    current_user: CurrentUser,
    periode: str = Query(default="semaine", pattern="^(semaine|mois|annee)$"),
):
    """Statistiques par membre d'un groupe — accessible au chef du groupe ou à un admin."""
    db = SessionLocal()
    try:
        groupe = db.query(Groupe).filter(Groupe.id == groupe_id).first()
        if not groupe:
            raise HTTPException(404, "Groupe introuvable")

        # Vérification d'accès : admin ou chef du groupe
        if current_user.role != "ADMIN":
            is_chef = db.execute(
                select(user_groups.c.is_chef).where(
                    user_groups.c.groupe_id == groupe_id,
                    user_groups.c.user_id == current_user.id,
                    user_groups.c.is_chef.is_(True),
                )
            ).first()
            if not is_chef:
                raise HTTPException(403, "Accès réservé au chef du groupe")

        now = datetime.now(timezone.utc)
        curr_start, curr_end, _, _ = _get_period_bounds(periode, now)

        # Récupérer les membres avec leur statut is_chef
        rows = db.execute(
            select(User, user_groups.c.is_chef)
            .join(user_groups, User.id == user_groups.c.user_id)
            .where(user_groups.c.groupe_id == groupe_id)
            .order_by(user_groups.c.is_chef.desc(), User.nom, User.prenom)
        ).all()

        membres = []
        for user, is_chef_flag in rows:
            nb_reponses = (
                db.query(func.count(Reponse.id))
                .join(Ticket, Reponse.ticket_id == Ticket.id)
                .filter(
                    Reponse.validator_id == user.id,
                    Reponse.statut.in_(["VALIDÉE", "CORRIGÉE"]),
                    Ticket.domaine == groupe.domaine,
                    Reponse.validated_at >= curr_start,
                    Reponse.validated_at < curr_end,
                )
                .scalar() or 0
            )

            nb_documents = (
                db.query(func.count(DocumentUpload.id))
                .filter(
                    DocumentUpload.user_id == user.id,
                    DocumentUpload.domaine == groupe.domaine,
                    DocumentUpload.created_at >= curr_start,
                    DocumentUpload.created_at < curr_end,
                )
                .scalar() or 0
            )

            membres.append({
                "id": str(user.id),
                "email": user.email,
                "prenom": user.prenom,
                "nom": user.nom,
                "is_chef": is_chef_flag,
                "nb_reponses_validees": nb_reponses,
                "nb_documents": nb_documents,
            })

        return {
            "groupe": {"id": str(groupe.id), "nom": groupe.nom, "domaine": groupe.domaine},
            "membres": membres,
        }
    finally:
        db.close()
