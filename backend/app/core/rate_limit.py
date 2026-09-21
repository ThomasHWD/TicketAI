"""Generic rate limiter backed by Valkey — fail-open (unlike login's fail-closed) because a Valkey blip must not"""

import logging

import redis as redis_lib
from fastapi import HTTPException, status

from app.config import settings

logger = logging.getLogger(__name__)


def limiter(nom: str, identifiant: str, max_par_fenetre: int, fenetre_secondes: int = 60) -> None:
    """Raise 429 when ``identifiant`` exceeds ``max_par_fenetre`` in the window. ``max_par_fenetre <= 0`` disables"""
    if max_par_fenetre <= 0:
        return

    try:
        r = redis_lib.from_url(settings.valkey_url, socket_connect_timeout=1)
        cle = f"rate:{nom}:{identifiant}"
        compte = r.incr(cle)
        r.expire(cle, fenetre_secondes, nx=True)
        if compte > max_par_fenetre:
            ttl = max(r.ttl(cle), 1)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Trop de requêtes. Réessayez dans {ttl} secondes.",
                headers={"Retry-After": str(ttl)},
            )
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("Limiteur de débit '%s' indisponible, requête laissée passer : %s", nom, exc)
