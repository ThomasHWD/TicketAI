from fastapi import APIRouter, HTTPException, Query, status

from app.config import settings
from app.core.rate_limit import limiter
from app.core.security import CurrentUser
from app.database import SessionLocal
from app.services.faq import rechercher_faq

router = APIRouter()

LONGUEUR_MIN = 3
LONGUEUR_MAX = 500


@router.get("/faq/recherche")
async def rechercher(
    current_user: CurrentUser,
    q: str = Query(..., description="Question posée en langage naturel"),
    limit: int | None = Query(None, ge=1, le=20),
):
    """Réponses canoniques sémantiquement proches de `q`, tous domaines confondus.

    `CurrentUser` et non `BackofficeUser` : c'est tout l'objet de la page. Aucun
    filtrage par domaine non plus — écart délibéré vis-à-vis de `check_domain_read`,
    et le seul possible, puisqu'un utilisateur lambda n'appartient à aucun groupe.
    Ce qui est exposé a été validé au moins `SEUIL_CANONIQUE` fois par un humain
    pour être diffusé tel quel.
    """
    question = q.strip()
    if len(question) < LONGUEUR_MIN:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"La question doit faire au moins {LONGUEUR_MIN} caractères.",
        )
    # Borne la charge envoyée à Albert plutôt que de rejeter : l'utilisateur a écrit
    # une vraie question, la tronquer sert mieux son intention qu'un 422.
    question = question[:LONGUEUR_MAX]

    # Avant l'appel Albert : une requête rejetée ne doit rien consommer du quota.
    limiter("faq", str(current_user.id), settings.faq_rate_limit_par_minute)

    db = SessionLocal()
    try:
        rangs = rechercher_faq(db, question, limit or settings.faq_max_resultats)
    finally:
        db.close()

    return {"question": question, **rangs}
