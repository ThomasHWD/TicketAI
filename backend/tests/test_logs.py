import io
import logging

import pytest
from app.core.logs import configurer_logs, delier, lier
from celery.app.trace import LOG_SUCCESS


@pytest.fixture
def journal():
    racine = logging.getLogger()
    handlers, niveau = racine.handlers[:], racine.level
    configurer_logs("INFO")
    # Not capsys: a handler created during fixture setup is bound to that phase's capture stream, closed afterwards.
    sortie = io.StringIO()
    racine.handlers[0].setStream(sortie)
    yield sortie.getvalue
    delier()
    racine.handlers, racine.level = handlers, niveau


def test_info_applicatif_ecrit_avec_le_prefixe_de_la_tache(journal):
    lier(tache="question_job:1a2b3c4d")
    logging.getLogger("app.workers.question").info("RAG → ticket %s", "abc")

    assert "INFO app.workers.question [tache=question_job:1a2b3c4d] RAG → ticket abc" in journal()


def test_ligne_succeeded_de_celery_sans_valeur_de_retour(journal):
    logging.getLogger("celery.app.trace").info(
        LOG_SUCCESS,
        {"name": "question_job", "id": "1a2b", "runtime": 0.5, "return_value": "{'question': 'mon arrêt maladie'}"},
    )

    sortie = journal()
    assert "Task question_job[1a2b] succeeded in 0.5s" in sortie
    assert "arrêt maladie" not in sortie
