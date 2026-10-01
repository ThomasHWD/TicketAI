"""Rewrites a validated follow-up as a self-contained question before indexing. Indexed under its bare text
(« et pour un apprenti ? »), it matched every thread ending with the same words, and the judge compared that thread
to an identical, context-free question B — the answer about another subject was served without review."""

import logging
import re

from app.config import settings
from app.services.llm import chat

logger = logging.getLogger(__name__)

_PROMPT_SYSTEME = (
    "Tu reformules des questions. On te donne, dans l'ordre, les questions qu'un utilisateur a posées "
    "dans un même fil. Réécris la DERNIÈRE en une seule question autonome, compréhensible sans le fil : "
    "reprends du fil uniquement ce qui lève ses références implicites (« et pour… », « dans ce cas… », "
    "pronoms). N'ajoute aucune condition absente du fil et ne réponds pas à la question. "
    "Rends uniquement la question reformulée, sur une seule ligne."
)

# a question, not a paragraph — longer output means the model answered or rambled
LONGUEUR_MAX = 400


def question_autonome(fil: list[str]) -> str | None:
    """Self-contained rewrite of the thread's last question. None = unusable output — never index a guess.
    Albert failures propagate so the caller can retry."""
    modele = settings.albert_garde_model_name or settings.albert_llm_model_name
    numerotees = "\n".join(f"{i}. {q}" for i, q in enumerate(fil, 1))
    brut = chat(
        [{"role": "system", "content": _PROMPT_SYSTEME}, {"role": "user", "content": numerotees}],
        temperature=0,
        max_tokens=120,
        model=modele,
    )
    return lire_reformulation(brut)


def lire_reformulation(brut: str) -> str | None:
    lignes = [ligne.strip() for ligne in brut.strip().splitlines() if ligne.strip()]
    if len(lignes) != 1:
        # Length only: the output is the user's question rephrased.
        logger.warning("reformulation inexploitable (%d lignes, %d caractères)", len(lignes), len(brut))
        return None
    texte = re.sub(r"^\d+[.)]\s*", "", lignes[0]).strip(" «»\"'")
    if not texte or len(texte) > LONGUEUR_MAX:
        logger.warning("reformulation inexploitable (%d caractères)", len(brut))
        return None
    return texte
