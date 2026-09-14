"""Tests unitaires pour le limiteur de débit (core/rate_limit.py).

Propriétés testées :
- max_par_fenetre <= 0 désactive la limite (aucun appel Redis)
- sous le seuil : pas de 429
- au-delà du seuil : 429 avec Retry-After
- Redis indisponible : fail-open (aucune exception)
"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException


def _limiter(nom, identifiant, max_par_fenetre, fenetre_secondes=60, *, compte=1):
    """Appelle limiter() avec un Redis mocké retournant `compte` comme valeur courante."""
    from app.core.rate_limit import limiter

    mock_r = MagicMock()
    mock_r.incr.return_value = compte
    mock_r.ttl.return_value = 30

    with patch("app.core.rate_limit.redis_lib.from_url", return_value=mock_r):
        limiter(nom, identifiant, max_par_fenetre, fenetre_secondes)

    return mock_r


class TestLimiter:
    def test_desactive_si_zero(self):
        """max_par_fenetre=0 court-circuite sans toucher Redis."""
        with patch("app.core.rate_limit.redis_lib.from_url") as mock_redis:
            from app.core.rate_limit import limiter
            limiter("faq", "user-1", 0)
        mock_redis.assert_not_called()

    def test_desactive_si_negatif(self):
        with patch("app.core.rate_limit.redis_lib.from_url") as mock_redis:
            from app.core.rate_limit import limiter
            limiter("faq", "user-1", -5)
        mock_redis.assert_not_called()

    def test_premiere_requete_initialise_expire(self):
        """Premier hit : expire est positionné sur la clé."""
        mock_r = _limiter("faq", "user-1", 20, compte=1)
        mock_r.expire.assert_called_once()

    def test_sous_le_seuil_ne_leve_pas(self):
        """Compte < max → aucune exception."""
        _limiter("faq", "user-1", 20, compte=19)  # ne lève pas

    def test_au_seuil_ne_leve_pas(self):
        """Compte == max → encore autorisé."""
        _limiter("faq", "user-1", 20, compte=20)

    def test_depasse_le_seuil_leve_429(self):
        """Compte > max → HTTPException 429."""
        with pytest.raises(HTTPException) as exc_info:
            _limiter("faq", "user-1", 20, compte=21)
        assert exc_info.value.status_code == 429
        assert "Retry-After" in exc_info.value.headers

    def test_retry_after_dans_les_headers(self):
        """Le header Retry-After contient le TTL renvoyé par Redis."""
        with patch("app.core.rate_limit.redis_lib.from_url") as mock_redis:
            mock_r = MagicMock()
            mock_r.incr.return_value = 21
            mock_r.ttl.return_value = 42
            mock_redis.return_value = mock_r

            from app.core.rate_limit import limiter
            with pytest.raises(HTTPException) as exc_info:
                limiter("faq", "user-1", 20)

        assert exc_info.value.headers["Retry-After"] == "42"

    def test_redis_indisponible_fail_open(self):
        """Si Redis lève, la requête passe (fail-open)."""
        from app.core.rate_limit import limiter

        with patch("app.core.rate_limit.redis_lib.from_url", side_effect=Exception("Redis down")):
            limiter("faq", "user-1", 20)  # ne lève pas

    @pytest.mark.parametrize("fenetre", [60, 86400])
    def test_fenetre_transmise_a_expire(self, fenetre):
        """La fenêtre (minute ou jour) est bien passée à expire()."""
        mock_r = _limiter("faq", "user-1", 10, fenetre_secondes=fenetre, compte=1)
        mock_r.expire.assert_called_once_with(mock_r.expire.call_args[0][0], fenetre)
