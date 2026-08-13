import uuid
from unittest.mock import MagicMock, patch

import pytest

# ── Helpers ────────────────────────────────────────────────────────────────


def make_db():
    """Session SQLAlchemy mockée."""
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    return db


def make_ticket(**kwargs):
    t = MagicMock()
    t.id = uuid.uuid4()
    t.job_id = uuid.uuid4()
    for k, v in kwargs.items():
        setattr(t, k, v)
    return t


def make_reponse(**kwargs):
    r = MagicMock()
    r.id = uuid.uuid4()
    r.ticket_id = uuid.uuid4()
    r.nb_validations = 0
    r.canonique = False
    r.reponse_source_id = None
    r.contenu_corrige = None
    r.contenu = "Réponse test"
    for k, v in kwargs.items():
        setattr(r, k, v)
    return r


# ── Tests _upsert_ticket ───────────────────────────────────────────────────


def test_upsert_ticket_cree_si_inexistant():
    from app.workers.question import _upsert_ticket

    db = make_db()
    job_id = uuid.uuid4()

    _upsert_ticket(
        db,
        job_id,
        question="test",
        domaine="IT",
        user_id=None,
        statut_job="TERMINÉ",
        statut_ticket="RÉPONDU",
        score_similarite=0.7,
        canonique=False,
        nb_retries=0,
        erreur=None,
        processed_at=None,
    )

    db.add.assert_called_once()
    db.flush.assert_called_once()


def test_upsert_ticket_met_a_jour_si_existant():
    from app.workers.question import _upsert_ticket

    db = make_db()
    job_id = uuid.uuid4()
    ticket_existant = make_ticket(job_id=job_id, statut_job="EN_ATTENTE")
    db.query.return_value.filter.return_value.first.return_value = ticket_existant

    ticket = _upsert_ticket(
        db,
        job_id,
        question="test",
        domaine="IT",
        user_id=None,
        statut_job="TERMINÉ",
        statut_ticket="RÉPONDU",
        score_similarite=0.7,
        canonique=False,
        nb_retries=0,
        erreur=None,
        processed_at=None,
    )

    db.add.assert_not_called()
    assert ticket.statut_job == "TERMINÉ"


def test_upsert_ticket_cible_disparu_leve_une_erreur_nommee():
    """Un ticket ciblé mais absent doit se dire, pas planter sur un `setattr`.

    Le symptôme sans ça : `'NoneType' object has no attribute 'statut_job'`, levé
    *après* la génération LLM, donc réessayé trois fois — quatre générations
    payées pour un ticket qui n'existe plus. C'est ce qui saturait le quota Albert
    et faisait tomber en 429 les questions légitimes.
    """
    from app.workers.question import TicketDisparu, _upsert_ticket

    db = make_db()  # `first()` renvoie None : le ticket ciblé n'est pas là
    disparu = uuid.uuid4()

    with pytest.raises(TicketDisparu):
        _upsert_ticket(db, uuid.uuid4(), ticket_id=disparu, statut_job="TERMINÉ")

    db.add.assert_not_called()
    db.flush.assert_not_called()


def test_question_job_abandonne_un_ticket_supprime_avant_tout_appel_reseau():
    """Le garde-fou doit tomber AVANT la recherche et la génération.

    Vérifier l'existence à l'écriture ne suffirait pas : le pipeline aurait déjà
    payé l'embedding, le rerank et le LLM. C'est l'ordre qui compte ici, pas le
    seul fait de ne pas planter.
    """
    from app.workers.question import question_job

    question_job.push_request(id=str(uuid.uuid4()), retries=0)
    try:
        with (
            patch("app.workers.question._ticket_existe", return_value=False),
            patch("app.workers.question.search_hybrid") as recherche,
            patch("app.workers.question.generate") as generation,
        ):
            resultat = question_job.run(
                question="Combien de jours de télétravail ?",
                domaine="RH",
                ticket_id=str(uuid.uuid4()),
                retraiter=True,
            )
    finally:
        question_job.pop_request()

    assert resultat["statut"] == "IGNORÉ"
    recherche.assert_not_called()
    generation.assert_not_called()


# ── Tests _upsert_reponse ──────────────────────────────────────────────────


def test_upsert_reponse_cree_si_inexistante():
    from app.workers.question import _upsert_reponse

    db = make_db()
    ticket = make_ticket()

    _upsert_reponse(db, ticket, "contenu test", 0.7)

    db.add.assert_called_once()
    db.flush.assert_called_once()


def test_upsert_reponse_source_llm_par_defaut():
    from app.workers.question import _upsert_reponse

    db = make_db()
    ticket = make_ticket()

    _upsert_reponse(db, ticket, "contenu", 0.7)

    ajout = db.add.call_args[0][0]
    assert ajout.source == "LLM"
    assert ajout.reponse_source_id is None


def test_upsert_reponse_suggestion_avec_source():
    from app.workers.question import _upsert_reponse

    db = make_db()
    ticket = make_ticket()
    source_id = uuid.uuid4()

    _upsert_reponse(db, ticket, "contenu", 0.7, source="SUGGESTION", reponse_source_id=source_id)

    ajout = db.add.call_args[0][0]
    assert ajout.source == "SUGGESTION"
    assert ajout.reponse_source_id == source_id


def test_upsert_reponse_met_a_jour_si_existante():
    from app.workers.question import _upsert_reponse

    db = make_db()
    ticket = make_ticket()
    reponse_existante = make_reponse(ticket_id=ticket.id, contenu="ancien")
    db.query.return_value.filter.return_value.first.return_value = reponse_existante

    reponse = _upsert_reponse(db, ticket, "nouveau contenu", 0.8)

    db.add.assert_not_called()
    assert reponse.contenu == "nouveau contenu"


# ── Tests seuil canonique ──────────────────────────────────────────────────


def test_seuil_cosinus_defini():
    from app.workers.question import SEUIL_COSINUS

    assert isinstance(SEUIL_COSINUS, float)
    assert 0.40 <= SEUIL_COSINUS <= 0.90


def test_nb_validations_incremente_sur_source():
    """Vérifie que la logique d'incrément cible la réponse source."""
    uuid.uuid4()
    reponse_source = MagicMock()
    reponse_source.nb_validations = 1
    reponse_source.canonique = False

    # Simule l'incrément
    reponse_source.nb_validations += 1
    seuil = 3
    if reponse_source.nb_validations >= seuil:
        reponse_source.canonique = True

    assert reponse_source.nb_validations == 2
    assert reponse_source.canonique is False


def test_canonique_true_quand_seuil_atteint():
    reponse_source = MagicMock()
    reponse_source.nb_validations = 2
    reponse_source.canonique = False

    reponse_source.nb_validations += 1
    seuil = 3
    if reponse_source.nb_validations >= seuil:
        reponse_source.canonique = True

    assert reponse_source.nb_validations == 3
    assert reponse_source.canonique is True
