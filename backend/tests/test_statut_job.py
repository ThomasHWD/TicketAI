"""GET /tickets/{job_id}/status must not hand the owner a text no human has reviewed.

The campaign of 29/09/2026 read the pending RAG answer through this route while /tickets/{id}/reponses hid it.
"""

from types import SimpleNamespace

import pytest

from .helpers_reponses import API, seed_ticket_reponse

pytestmark = pytest.mark.integration


def _job_termine(monkeypatch, ticket, reponse):
    import app.api.v1.tickets.submit as submit

    resultat = {
        "branche": "RAG",
        "question": ticket.question,
        "domaine": ticket.domaine,
        "reponse": reponse.contenu,  # frozen at generation
        "ticket_id": str(ticket.id),
        "reponse_id": str(reponse.id),
    }
    monkeypatch.setattr(submit, "AsyncResult", lambda *_a, **_k: SimpleNamespace(status="SUCCESS", result=resultat))


@pytest.mark.parametrize(
    ("statut", "contenu_corrige", "attendu"),
    [
        ("EN_ATTENTE", None, None),
        ("REJETÉE", None, None),
        ("VALIDÉE", None, "Texte généré"),
        ("CORRIGÉE", "Texte corrigé", "Texte corrigé"),
    ],
)
def test_le_proprietaire_ne_lit_que_le_texte_relu(
    client, db_session, user_factory, auth_header, monkeypatch, statut, contenu_corrige, attendu
):
    employe = user_factory("USER")
    ticket, reponse = seed_ticket_reponse(
        db_session, user_id=employe.id, statut=statut, contenu="Texte généré", contenu_corrige=contenu_corrige
    )
    _job_termine(monkeypatch, ticket, reponse)

    resp = client.get(f"{API}/tickets/job-1/status", headers=auth_header(employe))

    assert resp.status_code == 200
    assert resp.json()["reponse"] == attendu


def test_le_relecteur_du_domaine_lit_le_texte_en_attente(
    client, db_session, user_factory, validator, auth_header, monkeypatch
):
    ticket, reponse = seed_ticket_reponse(db_session, user_id=user_factory("USER").id, contenu="Texte généré")
    _job_termine(monkeypatch, ticket, reponse)

    resp = client.get(f"{API}/tickets/job-1/status", headers=auth_header(validator))

    assert resp.json()["reponse"] == "Texte généré"
