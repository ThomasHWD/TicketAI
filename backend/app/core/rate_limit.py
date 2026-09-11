"""Garde-fou de débit générique, adossé à Valkey.

Généralise le motif de `_check_login_rate` (api/v1/auth.py), avec une différence
assumée : **fail-open**. Le login se ferme (503) parce qu'il protège des
identifiants ; les routes de lecture, elles, ne doivent pas devenir inutilisables
parce que Valkey hoquette — d'autant que Valkey est aussi le broker Celery, donc
son indisponibilité se voit largement ailleurs.
"""

import logging

import redis as redis_lib
from fastapi import HTTPException, status

from app.config import settings

logger = logging.getLogger(__name__)


def limiter(nom: str, identifiant: str, max_par_fenetre: int, fenetre_secondes: int = 60) -> None:
    """Lève un 429 si `identifiant` dépasse `max_par_fenetre` sur la fenêtre glissante.

    `max_par_fenetre <= 0` désactive la limite — c'est ce qui rend le réglage
    débrayable depuis le `.env` sans toucher au code.
    """
    if max_par_fenetre <= 0:
        return

    try:
        r = redis_lib.from_url(settings.valkey_url, socket_connect_timeout=1)
        cle = f"rate:{nom}:{identifiant}"
        compte = r.incr(cle)
        if compte == 1:
            r.expire(cle, fenetre_secondes)
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
