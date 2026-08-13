"""Tests d'intégration du fil de conversation : précisions (/suivi) et clôture
(/cloturer) sur un ticket, plus le comportement « mode suivi » du worker.

Marqués ``integration`` : exécutés en CI (Postgres), auto-skippés en local sans
infra (cf. ``conftest.py``). ``question_job.apply_async`` (enqueue Celery/Valkey)
est mocké pour rester déterministe sans worker.
"""

import uuid
from unittest.mock import MagicMock

import pytest
from app.models.groupe import Groupe
from app.models.reponse import Reponse
from app.models.ticket import Ticket
from app.models.user import User
from app.workers.question import (
    _charger_contexte_fil,
    _upsert_reponse,
    _upsert_ticket,
)

pytestmark = pytest.mark.integration

API = "/api/v1"


# --------------------------------------------------------------------------- #
# Helpers de seed
# --------------------------------------------------------------------------- #
def seed_ticket_reponse(
    db,
    *,
    question="Question initiale ?",
    domaine="IT",
    ticket_statut="VALIDÉ",
    reponse_statut="VALIDÉE",
    closed_at=None,
    user_id=None,
):
    ticket = Ticket(
        question=question,
        domaine=domaine,
        statut_ticket=ticket_statut,
        closed_at=closed_at,
        user_id=user_id,
    )
    db.add(ticket)
    db.flush()
    reponse = Reponse(
        ticket_id=ticket.id,
        contenu="Réponse initiale",
        statut=reponse_statut,
        source="LLM",
    )
    db.add(reponse)
    db.commit()
    db.refresh(ticket)
    db.refresh(reponse)
    return ticket, reponse


@pytest.fixture
def owner(db_session):
    """Utilisateur lambda (sans groupe) propriétaire des tickets de test."""
    user = User(email=f"{uuid.uuid4()}@test.local", role="USER")
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def backoffice_user(db_session):
    """Utilisateur backoffice membre du groupe IT."""
    user = User(email=f"{uuid.uuid4()}@test.local", role="VALIDATEUR")
    db_session.add(user)
    groupe = Groupe(nom="IT-thread", domaine="IT")
    db_session.add(groupe)
    db_session.flush()
    groupe.membres.append(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def mock_question_job(monkeypatch):
    """Neutralise l'enqueue Celery de ``question_job`` déclenché par /suivi."""
    import app.api.v1.tickets as tickets_module

    job = MagicMock()
    job.id = "job-test-123"
    mock = MagicMock(return_value=job)
    monkeypatch.setattr(tickets_module.question_job, "apply_async", mock)
    return mock


# --------------------------------------------------------------------------- #
# POST /tickets/{id}/suivi
# --------------------------------------------------------------------------- #
def test_suivi_enqueue_le_job_sur_le_ticket_existant(client, db_session, mock_question_job, owner, auth_header):
    ticket, _ = seed_ticket_reponse(db_session, domaine="RH", user_id=owner.id)

    resp = client.post(
        f"{API}/tickets/{ticket.id}/suivi",
        json={"question": "Et pour un CDD ?"},
        headers=auth_header(owner),
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["statut"] == "EN_ATTENTE"
    assert body["ticket_id"] == str(ticket.id)

    mock_question_job.assert_called_once()
    call = mock_question_job.call_args
    # La précision + le domaine du ticket sont passés en args ; le ticket_id
    # cible le ticket existant (mode suivi).
    assert call.kwargs["args"][0] == "Et pour un CDD ?"
    assert call.kwargs["args"][1] == "RH"
    assert call.kwargs["kwargs"]["ticket_id"] == str(ticket.id)
    assert call.kwargs["queue"] == "queue_questions"

    # Le ticket est marqué « en cours » dès la soumission (badges des listes).
    db_session.expire_all()
    assert db_session.get(Ticket, ticket.id).statut_job == "EN_ATTENTE"


def test_suivi_ticket_cloture_renvoie_409(client, db_session, mock_question_job, owner, auth_header):
    from datetime import datetime, timezone

    ticket, _ = seed_ticket_reponse(db_session, closed_at=datetime.now(timezone.utc), user_id=owner.id)

    resp = client.post(
        f"{API}/tickets/{ticket.id}/suivi",
        json={"question": "Une précision"},
        headers=auth_header(owner),
    )

    assert resp.status_code == 409
    mock_question_job.assert_not_called()


def test_suivi_question_vide_renvoie_400(client, db_session, mock_question_job, auth_headers):
    ticket, _ = seed_ticket_reponse(db_session)

    resp = client.post(
        f"{API}/tickets/{ticket.id}/suivi",
        json={"question": "   "},
        headers=auth_headers,
    )

    assert resp.status_code == 400
    mock_question_job.assert_not_called()


def test_suivi_ticket_introuvable_renvoie_404(client, db_session, mock_question_job, auth_headers):
    resp = client.post(
        f"{API}/tickets/{uuid.uuid4()}/suivi",
        json={"question": "Une précision"},
        headers=auth_headers,
    )

    assert resp.status_code == 404


# --------------------------------------------------------------------------- #
# POST /tickets/{id}/cloturer
# --------------------------------------------------------------------------- #
def test_cloturer_pose_closed_at(client, db_session, owner, auth_header):
    ticket, _ = seed_ticket_reponse(db_session, user_id=owner.id)

    resp = client.post(f"{API}/tickets/{ticket.id}/cloturer", headers=auth_header(owner))

    assert resp.status_code == 200
    assert resp.json()["closed_at"] is not None

    db_session.expire_all()
    assert db_session.get(Ticket, ticket.id).closed_at is not None


def test_cloturer_deja_cloture_renvoie_409(client, db_session, owner, auth_header):
    from datetime import datetime, timezone

    ticket, _ = seed_ticket_reponse(db_session, closed_at=datetime.now(timezone.utc), user_id=owner.id)

    resp = client.post(f"{API}/tickets/{ticket.id}/cloturer", headers=auth_header(owner))

    assert resp.status_code == 409


# --------------------------------------------------------------------------- #
# GET /tickets/{id}/reponses  expose question_suivi
# --------------------------------------------------------------------------- #
def test_reponses_exposent_question_suivi(client, db_session, owner, auth_header):
    ticket, _ = seed_ticket_reponse(db_session, user_id=owner.id)
    db_session.add(
        Reponse(
            ticket_id=ticket.id,
            contenu="Réponse à la précision",
            statut="EN_ATTENTE",
            source="LLM",
            question_suivi="Et pour un CDD ?",
        )
    )
    db_session.commit()

    resp = client.get(f"{API}/tickets/{ticket.id}/reponses", headers=auth_header(owner))

    assert resp.status_code == 200
    items = resp.json()
    suivis = [r["question_suivi"] for r in items]
    assert None in suivis  # réponse initiale
    assert "Et pour un CDD ?" in suivis  # tour de suivi


# --------------------------------------------------------------------------- #
# Worker : mode suivi (helpers)
# --------------------------------------------------------------------------- #
def test_upsert_reponse_mode_suivi_ajoute_sans_ecraser(db_session):
    ticket, initiale = seed_ticket_reponse(db_session)

    nouvelle = _upsert_reponse(
        db_session,
        ticket,
        "Réponse au suivi",
        0.5,
        question_suivi="Ma précision",
        nouveau=True,
    )
    db_session.commit()

    assert nouvelle.id != initiale.id
    assert nouvelle.question_suivi == "Ma précision"
    reponses = db_session.query(Reponse).filter(Reponse.ticket_id == ticket.id).all()
    assert len(reponses) == 2
    # La réponse initiale n'a pas été écrasée.
    assert db_session.get(Reponse, initiale.id).contenu == "Réponse initiale"


def test_canoniques_affiche_la_question_de_la_precision(client, db_session, backoffice_user, auth_header):
    """Une réponse canonique issue d'un suivi doit s'afficher avec le texte de la
    précision (`question_suivi`), pas la question initiale du ticket."""
    ticket, _ = seed_ticket_reponse(db_session, question="Question initiale ?")
    db_session.add(
        Reponse(
            ticket_id=ticket.id,
            contenu="Réponse canonique de la précision",
            statut="VALIDÉE",
            source="LLM",
            canonique=True,
            question_suivi="Et pour un CDD ?",
        )
    )
    db_session.commit()

    resp = client.get(
        f"{API}/reponses/canoniques",
        params={"page": 1, "limit": 20},
        headers=auth_header(backoffice_user),
    )

    assert resp.status_code == 200
    questions = [item["question"] for item in resp.json()["items"]]
    assert "Et pour un CDD ?" in questions
    assert "Question initiale ?" not in questions


def test_feedback_indexe_la_precision_sous_sa_propre_question(db_session, monkeypatch):
    """Une réponse de suivi validée doit être indexée sous le texte de la précision
    (`question_suivi`), pas sous la question initiale du ticket — sinon elle ne
    pourrait jamais devenir canonique pour la bonne question."""
    import app.workers.feedback as feedback_module

    ticket, _ = seed_ticket_reponse(db_session, question="Question initiale ?")
    precision = Reponse(
        ticket_id=ticket.id,
        contenu="Réponse à la précision",
        statut="VALIDÉE",
        source="LLM",
        question_suivi="Et pour un CDD ?",
    )
    db_session.add(precision)
    db_session.commit()

    captured = {}

    def fake_embed(texts):
        captured["texts"] = texts
        return [{"dense": [0.1], "sparse": {"indices": [0], "values": [0.2]}}]

    upsert_mock = MagicMock()
    monkeypatch.setattr(feedback_module, "embed_texts", fake_embed)
    monkeypatch.setattr(feedback_module.client, "upsert", upsert_mock)

    feedback_module.feedback_job.apply(args=[str(precision.id)], throw=True)

    # Le texte embarqué est la précision, pas la question initiale.
    assert captured["texts"] == ["Et pour un CDD ?"]
    assert upsert_mock.called


def test_upsert_ticket_mode_suivi_ne_reecrit_pas_la_question(db_session):
    ticket, _ = seed_ticket_reponse(db_session, question="Question initiale ?", domaine="IT")

    _upsert_ticket(
        db_session,
        uuid.uuid4(),
        ticket_id=ticket.id,
        question="Une précision différente",
        domaine="RH",
        statut_job="TERMINÉ",
        statut_ticket="RÉPONDU",
    )
    db_session.commit()

    db_session.expire_all()
    reloaded = db_session.get(Ticket, ticket.id)
    # La question et le domaine d'origine sont préservés ; seul le cycle change.
    assert reloaded.question == "Question initiale ?"
    assert reloaded.domaine == "IT"
    assert reloaded.statut_job == "TERMINÉ"


# --------------------------------------------------------------------------- #
# Worker : contexte du fil pour une précision (_charger_contexte_fil)
# --------------------------------------------------------------------------- #
def test_charger_contexte_fil_construit_historique_et_requete(db_session):
    """Une précision doit être traitée AVEC le contexte du fil : historique LLM
    alterné user/assistant et requête de recherche concaténant les intentions
    utilisateur (question d'origine + précisions + précision courante)."""
    ticket, initiale = seed_ticket_reponse(db_session, question="Comment poser mes congés payés ?")
    # Un tour de suivi déjà validé dans le fil.
    db_session.add(
        Reponse(
            ticket_id=ticket.id,
            contenu="Réponse au premier suivi",
            contenu_corrige="Réponse corrigée au premier suivi",
            statut="VALIDÉE",
            source="LLM",
            question_suivi="Combien de jours par an ?",
        )
    )
    db_session.commit()

    historique, requete = _charger_contexte_fil(ticket.id, "Et pour un CDD ?")

    # Historique : Q initiale → réponse initiale → précision → sa réponse (corrigée).
    assert historique == [
        {"role": "user", "content": "Comment poser mes congés payés ?"},
        {"role": "assistant", "content": "Réponse initiale"},
        {"role": "user", "content": "Combien de jours par an ?"},
        {"role": "assistant", "content": "Réponse corrigée au premier suivi"},
    ]
    # Requête de recherche : uniquement les tours utilisateur + la précision courante.
    assert requete == ("Comment poser mes congés payés ?\nCombien de jours par an ?\nEt pour un CDD ?")


def test_charger_contexte_fil_ticket_introuvable(db_session):
    historique, requete = _charger_contexte_fil(uuid.uuid4(), "Et pour un CDD ?")
    assert historique == []
    assert requete == "Et pour un CDD ?"


def test_question_job_suivi_contextualise_recherche_et_generation(db_session, monkeypatch):
    """En mode suivi et hors réutilisation, la branche RAG doit :
    - refaire une recherche CONTEXTUALISÉE (requête = intentions du fil) ;
    - appeler ``generate`` avec un historique non vide (question d'origine…)."""
    import app.workers.question as q

    ticket, _ = seed_ticket_reponse(db_session, question="Comment poser mes congés payés ?", domaine="RH")

    # Chunk sans reponse_id → aucune réutilisation possible → branche RAG.
    chunk = {
        "score_cosinus": 0.5,
        "rerank_score": 0.9,
        "source": "doc.md",
        "contenu": "Texte source",
        "doc_id": str(uuid.uuid4()),
        "chunk_index": 0,
        "reponse_id": None,
    }
    search_mock = MagicMock(return_value=[chunk])
    rerank_mock = MagicMock(return_value=[chunk])
    generate_mock = MagicMock(return_value=("Réponse contextuelle", False))
    monkeypatch.setattr(q, "search_hybrid", search_mock)
    monkeypatch.setattr(q, "rerank", rerank_mock)
    monkeypatch.setattr(q, "generate", generate_mock)

    q.question_job.apply(
        args=["Et pour un CDD ?", "RH", None],
        kwargs={"ticket_id": str(ticket.id)},
        throw=True,
    )

    # generate reçoit l'historique du fil (question d'origine en tête).
    assert generate_mock.called
    historique = generate_mock.call_args.kwargs["historique"]
    assert historique
    assert historique[0] == {
        "role": "user",
        "content": "Comment poser mes congés payés ?",
    }
    # Une recherche a bien été contextualisée (intentions du fil concaténées),
    # en plus de la recherche initiale sur la précision brute.
    requetes = [call.args[0] for call in search_mock.call_args_list]
    assert "Comment poser mes congés payés ?\nEt pour un CDD ?" in requetes
    # Le rerank utilise également la requête contextualisée.
    assert rerank_mock.call_args.args[0] == ("Comment poser mes congés payés ?\nEt pour un CDD ?")


def test_upsert_ticket_mode_suivi_rebascule_le_statut(db_session):
    """Une précision en attente doit rebasculer statut/canonique du ticket pour
    que les badges repassent en « en cours » (et non rester « Répondu »)."""
    ticket, _ = seed_ticket_reponse(db_session, ticket_statut="VALIDÉ")
    ticket.canonique = True
    db_session.commit()

    _upsert_ticket(
        db_session,
        uuid.uuid4(),
        ticket_id=ticket.id,
        statut_job="TERMINÉ",
        statut_ticket="RÉPONDU",
        canonique=False,
    )
    db_session.commit()

    db_session.expire_all()
    reloaded = db_session.get(Ticket, ticket.id)
    assert reloaded.statut_ticket == "RÉPONDU"
    assert reloaded.canonique is False
