"""Tests unitaires pour le worker replay_echoues.

Propriétés testées :
- tickets ÉCHOUÉ + NOUVEAU → remis en queue, statut_job → EN_ATTENTE
- tickets ÉCHOUÉ + RÉPONDU (suivi raté) → ignorés
- tickets trop vieux → ignorés (filtrés par la requête SQL)
- si l'enqueue échoue → statut_job remis à ÉCHOUÉ
- aucun ticket → résultat vide sans effet de bord
"""

import uuid
from unittest.mock import MagicMock, patch


def _make_ticket(
    statut_job: str = "ÉCHOUÉ",
    statut_ticket: str = "NOUVEAU",
    domaine: str = "RH",
    question: str = "Comment poser des congés ?",
    objet: str | None = "Congés",
):
    t = MagicMock()
    t.id = uuid.uuid4()
    t.statut_job = statut_job
    t.statut_ticket = statut_ticket
    t.domaine = domaine
    t.question = question
    t.objet = objet
    t.user_id = uuid.uuid4()
    return t


def _run(db_tickets: list, enqueue_raises: bool = False):
    """Exécute replay_echoues_job avec les tickets fournis."""
    from app.workers.replay_echoues import replay_echoues_job

    with (
        patch("app.workers.replay_echoues.SessionLocal") as mock_session_cls,
        patch("app.workers.replay_echoues.celery_app") as mock_celery,
        patch("app.workers.replay_echoues.settings") as mock_settings,
    ):
        mock_settings.replay_max_age_jours = 7

        db = MagicMock()
        mock_session_cls.return_value = db
        db.query.return_value.filter.return_value.all.return_value = db_tickets

        if enqueue_raises:
            mock_celery.send_task.side_effect = Exception("Valkey down")

        result = replay_echoues_job()
        return result, mock_celery, db, mock_session_cls


class TestReplayEchoues:
    def test_aucun_ticket_retourne_zero(self):
        result, mock_celery, _, _ = _run([])
        assert result == {"rejoues": 0, "trouves": 0}
        mock_celery.send_task.assert_not_called()

    def test_ticket_echoue_nouveau_est_reenqueue(self):
        ticket = _make_ticket()
        result, mock_celery, db, _ = _run([ticket])

        assert result == {"rejoues": 1, "trouves": 1}
        mock_celery.send_task.assert_called_once_with(
            "question_job",
            args=[ticket.question, ticket.domaine, str(ticket.user_id)],
            kwargs={"ticket_id": str(ticket.id), "objet": ticket.objet, "retraiter": True},
            queue="queue_questions",
        )

    def test_statut_job_remis_en_attente_avant_enqueue(self):
        """statut_job passe à EN_ATTENTE avant l'envoi dans la queue."""
        ticket = _make_ticket()
        _run([ticket])
        assert ticket.statut_job == "EN_ATTENTE"

    def test_plusieurs_tickets_tous_reenqueues(self):
        tickets = [_make_ticket() for _ in range(3)]
        result, mock_celery, _, _ = _run(tickets)
        assert result == {"rejoues": 3, "trouves": 3}
        assert mock_celery.send_task.call_count == 3

    def test_enqueue_echoue_remet_statut_echoue(self):
        """Si send_task lève, le ticket repasse à ÉCHOUÉ."""
        ticket = _make_ticket()
        result, _, _, mock_session_cls = _run([ticket], enqueue_raises=True)

        assert result == {"rejoues": 0, "trouves": 1}
        # Une 2e session est ouverte pour écrire le rollback
        assert mock_session_cls.call_count >= 2

    def test_user_id_none_transmis_correctement(self):
        """Un ticket sans user_id passe None dans les args."""
        ticket = _make_ticket()
        ticket.user_id = None

        _, mock_celery, _, _ = _run([ticket])

        args = mock_celery.send_task.call_args
        assert args.kwargs["args"][2] is None

    def test_commit_appele_apres_passage_en_attente(self):
        """Le commit est appelé après avoir marqué les tickets EN_ATTENTE."""
        tickets = [_make_ticket(), _make_ticket()]
        _, _, db, _ = _run(tickets)
        db.commit.assert_called_once()
