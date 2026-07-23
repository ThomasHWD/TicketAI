"""Tests unitaires de ``generate`` : assemblage des messages envoyés au LLM.

Mockent ``httpx.post`` → pas d'appel réseau, pas d'infra requise.
"""

from unittest.mock import MagicMock

import app.services.llm as llm

CHUNK = {"source": "doc.md", "rerank_score": 0.5, "contenu": "Extrait"}


def _fake_response(content="ok"):
    resp = MagicMock()
    resp.raise_for_status.return_value = None
    resp.json.return_value = {"choices": [{"message": {"content": content}}]}
    return resp


def test_generate_sans_historique_system_puis_user(monkeypatch):
    post = MagicMock(return_value=_fake_response())
    monkeypatch.setattr(llm.httpx, "post", post)

    llm.generate("Ma question", [CHUNK])

    messages = post.call_args.kwargs["json"]["messages"]
    assert [m["role"] for m in messages] == ["system", "user"]
    assert "Ma question" in messages[-1]["content"]


def test_generate_avec_historique_insere_les_tours_avant_la_question(monkeypatch):
    post = MagicMock(return_value=_fake_response())
    monkeypatch.setattr(llm.httpx, "post", post)

    historique = [
        {"role": "user", "content": "Comment poser mes congés ?"},
        {"role": "assistant", "content": "Voici la procédure…"},
    ]
    llm.generate("Et pour un CDD ?", [CHUNK], historique=historique)

    messages = post.call_args.kwargs["json"]["messages"]
    # L'historique s'insère entre le system et la question courante.
    assert [m["role"] for m in messages] == [
        "system",
        "user",
        "assistant",
        "user",
    ]
    assert messages[1]["content"] == "Comment poser mes congés ?"
    assert messages[2]["content"] == "Voici la procédure…"
    assert "Et pour un CDD ?" in messages[-1]["content"]
    # Le system prompt mentionne la prise en compte de l'historique.
    assert "historique" in messages[0]["content"].lower()
