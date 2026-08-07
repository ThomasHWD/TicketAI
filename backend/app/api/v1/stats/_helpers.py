from datetime import datetime, timedelta, timezone

from sqlalchemy import func

from app.models.ticket import Ticket


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


def _variation_taux(curr_count: int, curr_total: int, prev_count: int, prev_total: int) -> dict:
    """Variation exprimée en taux (%). La variation est en points de pourcentage."""
    curr_taux = round(curr_count / curr_total * 100, 1) if curr_total > 0 else 0.0
    prev_taux = round(prev_count / prev_total * 100, 1) if prev_total > 0 else 0.0
    diff = round(curr_taux - prev_taux, 1)
    return {"valeur": curr_taux, "count": curr_count, "variation": diff, "hausse": curr_taux >= prev_taux}


def _variation_temps(curr: float, prev: float) -> dict:
    """Variation pour les métriques de temps : hausse = temps augmente = mauvais."""
    if prev == 0:
        pct = 0.0
    else:
        pct = round((curr - prev) / prev * 100, 1)
    return {"valeur": curr, "variation": pct, "hausse": curr <= prev}


def _avg_satisfaction(db, start: datetime, end: datetime, domain_filters: list) -> dict:
    row = (
        db.query(
            func.avg(Ticket.note_qualite).label("avg_qualite"),
            func.avg(Ticket.note_delai).label("avg_delai"),
            func.count(Ticket.id).filter(Ticket.note_qualite.isnot(None)).label("nb"),
        )
        .filter(Ticket.closed_at >= start, Ticket.closed_at < end, *domain_filters)
        .first()
    )
    return {
        "avg_qualite": round(float(row.avg_qualite), 2) if row.avg_qualite else None,
        "avg_delai": round(float(row.avg_delai), 2) if row.avg_delai else None,
        "nb_avec_notes": row.nb or 0,
    }
