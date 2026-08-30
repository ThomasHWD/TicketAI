"""Tests unitaires pour le worker auto_cloture.

Vérifie la logique de clôture automatique des tickets validés inactifs.
Tous les effets de bord (Redis, broadcast SSE) sont mockés.
"""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

# ── Helpers ────────────────────────────────────────────────────────────────────


def _make_ticket(
    statut_ticket: str = "VALIDÉ",
    closed_at=None,
    validated_at=None,
    domaine: str = "RH",
):
    t = MagicMock()
    t.id = uuid.uuid4()
    t.statut_ticket = statut_ticket
    t.closed_at = closed_at
    t.validated_at = validated_at
    t.domaine = domaine
    return t


# ── Tests ──────────────────────────────────────────────────────────────────────


class TestAutoCloture:
    """Tests de la tâche Celery auto_cloture_job."""

    def _run(self, db_tickets: list, jours: int = 7):
        """Exécute auto_cloture_job avec les tickets fournis et retourne le résultat."""
        from app.workers.auto_cloture import auto_cloture_job

        with (
            patch("app.workers.auto_cloture.SessionLocal") as mock_session_cls,
            patch("app.workers.auto_cloture.broadcast_sync") as mock_broadcast,
            patch("app.workers.auto_cloture.redis_lib.from_url") as mock_redis,
            patch("app.workers.auto_cloture.settings") as mock_settings,
        ):
            mock_settings.valkey_url = "redis://localhost:6379/0"
            mock_settings.jours_auto_cloture = jours

            mock_r = MagicMock()
            mock_redis.return_value = mock_r

            db = MagicMock()
            db.__enter__ = MagicMock(return_value=db)
            db.__exit__ = MagicMock(return_value=False)
            mock_session_cls.return_value = db
            db.query.return_value.filter.return_value.all.return_value = db_tickets

            result = auto_cloture_job()
            return result, mock_broadcast, db

    def test_aucun_ticket_eligible(self):
        """Sans ticket éligible, retourne 0 clôture et n'émet aucun broadcast."""
        result, mock_broadcast, _ = self._run([])
        assert result == {"clotures": 0}
        mock_broadcast.assert_not_called()

    def test_cloture_un_ticket(self):
        """Un ticket VALIDÉ inactif est clôturé et déclenche un broadcast."""
        ticket = _make_ticket(validated_at=datetime.now(timezone.utc) - timedelta(days=8))
        result, mock_broadcast, db = self._run([ticket])

        assert result == {"clotures": 1}
        assert ticket.closed_at is not None
        mock_broadcast.assert_called_once_with(
            f"sse:domain:{ticket.domaine}",
            "ticket_closed",
            {"ticket_id": str(ticket.id), "domaine": ticket.domaine},
        )
        db.commit.assert_called_once()

    def test_cloture_plusieurs_tickets_meme_domaine(self):
        """Plusieurs tickets d'un même domaine déclenchent autant de broadcasts."""
        t1 = _make_ticket(domaine="IT", validated_at=datetime.now(timezone.utc) - timedelta(days=10))
        t2 = _make_ticket(domaine="IT", validated_at=datetime.now(timezone.utc) - timedelta(days=15))
        result, mock_broadcast, _ = self._run([t1, t2])

        assert result == {"clotures": 2}
        assert mock_broadcast.call_count == 2

    def test_cloture_tickets_domaines_differents(self):
        """Des tickets de domaines distincts déclenchent des broadcasts distincts."""
        t1 = _make_ticket(domaine="RH", validated_at=datetime.now(timezone.utc) - timedelta(days=10))
        t2 = _make_ticket(domaine="IT", validated_at=datetime.now(timezone.utc) - timedelta(days=10))
        result, mock_broadcast, _ = self._run([t1, t2])

        assert result == {"clotures": 2}
        channels = {c.args[0] for c in mock_broadcast.call_args_list}
        assert "sse:domain:RH" in channels
        assert "sse:domain:IT" in channels

    def test_closed_at_est_defini_sur_chaque_ticket(self):
        """Chaque ticket clôturé reçoit une date closed_at."""
        tickets = [_make_ticket(validated_at=datetime.now(timezone.utc) - timedelta(days=8)) for _ in range(3)]
        self._run(tickets)
        for t in tickets:
            assert t.closed_at is not None

    def test_redis_heartbeat_est_mis_a_jour(self):
        """Le heartbeat Redis est écrit au début de chaque exécution."""
        from app.workers.auto_cloture import BEAT_HEARTBEAT_KEY

        with (
            patch("app.workers.auto_cloture.SessionLocal") as mock_session_cls,
            patch("app.workers.auto_cloture.broadcast_sync"),
            patch("app.workers.auto_cloture.redis_lib.from_url") as mock_redis,
            patch("app.workers.auto_cloture.settings") as mock_settings,
        ):
            from app.workers.auto_cloture import auto_cloture_job as _job

            mock_settings.valkey_url = "redis://localhost:6379/0"
            mock_settings.jours_auto_cloture = 7
            mock_r = MagicMock()
            mock_redis.return_value = mock_r
            db = MagicMock()
            mock_session_cls.return_value = db
            db.query.return_value.filter.return_value.all.return_value = []

            _job()

            mock_r.set.assert_called_once()
            args = mock_r.set.call_args
            assert args[0][0] == BEAT_HEARTBEAT_KEY

    def test_redis_indisponible_ne_bloque_pas(self):
        """Si Redis est indisponible, la clôture se déroule quand même (fail-open)."""
        ticket = _make_ticket(validated_at=datetime.now(timezone.utc) - timedelta(days=8))

        with (
            patch("app.workers.auto_cloture.SessionLocal") as mock_session_cls,
            patch("app.workers.auto_cloture.broadcast_sync"),
            patch("app.workers.auto_cloture.redis_lib.from_url", side_effect=Exception("Redis down")),
            patch("app.workers.auto_cloture.settings") as mock_settings,
        ):
            from app.workers.auto_cloture import auto_cloture_job as _job

            mock_settings.valkey_url = "redis://localhost:6379/0"
            mock_settings.jours_auto_cloture = 7
            db = MagicMock()
            mock_session_cls.return_value = db
            db.query.return_value.filter.return_value.all.return_value = [ticket]

            result = _job()
            assert result == {"clotures": 1}
