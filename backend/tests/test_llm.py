"""Tests unitaires de ``generate`` : assemblage des messages envoyés au LLM.

Mockent ``httpx.post`` → pas d'appel réseau, pas d'infra requise.
"""

from unittest.mock import MagicMock

import app.services.llm as llm
import pytest

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


def test_generate_enonce_la_hierarchie_des_regles(monkeypatch):
    """Lex specialis : la règle spécifique l'emporte, et l'absence d'extrait se dit.

    Sans cette consigne, « le télétravail est-il possible pour les alternants ? »
    reçoit la règle générale — soit parce que le modèle ignore l'exception qu'il
    a pourtant sous les yeux, soit parce qu'aucun extrait ne la porte et qu'il
    applique le cas général par défaut. La dernière phrase traite le second cas
    et compte autant que la première.
    """
    post = MagicMock(return_value=_fake_response())
    monkeypatch.setattr(llm.httpx, "post", post)

    llm.generate("Ma question", [CHUNK])

    systeme = post.call_args.kwargs["json"]["messages"][0]["content"]
    assert "la règle spécifique l'emporte sur la générale" in systeme
    assert "dis-le au lieu d'appliquer la règle générale par défaut" in systeme


def test_generate_montre_le_chunk_avec_son_locateur(monkeypatch):
    """La génération lit le texte **indexé**, pas le chunk nu.

    « Les intéressés en sont exclus » est inexploitable seul : c'est le locateur
    qui dit de quelle règle ils sont exclus. Repli sur `contenu` pour les points
    indexés avant la contextualisation.
    """
    post = MagicMock(return_value=_fake_response())
    monkeypatch.setattr(llm.httpx, "post", post)

    llm.generate(
        "Ma question",
        [
            {"rerank_score": 0.9, "contenu": "brut A", "contenu_indexe": "locateur\n\nbrut A"},
            {"rerank_score": 0.5, "contenu": "brut B"},
        ],
    )

    contexte = post.call_args.kwargs["json"]["messages"][-1]["content"]
    assert "locateur\n\nbrut A" in contexte
    assert "brut B" in contexte


@pytest.mark.parametrize(
    "brut, texte, hors_domaine",
    [
        ("[HORS_DOMAINE] Rien sur ce sujet.", "Rien sur ce sujet.", True),
        ("  **[HORS_DOMAINE]** Rien sur ce sujet.", "Rien sur ce sujet.", True),  # `startswith` le ratait
        ("« [HORS_DOMAINE] » : Rien sur ce sujet.", "Rien sur ce sujet.", True),
        ("Le préavis est d'un mois. [HORS_DOMAINE]", "Le préavis est d'un mois.", False),  # jamais montré brut
        ("Le préavis est d'un mois.", "Le préavis est d'un mois.", False),
    ],
)
def test_lire_marqueur(brut, texte, hors_domaine):
    from app.services.llm import lire_marqueur

    assert lire_marqueur(brut) == (texte, hors_domaine)
