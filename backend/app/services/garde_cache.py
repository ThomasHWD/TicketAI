"""Guard for the canonical cache: verifies the question asks exactly the same thing as the indexed question before"""

import logging
import re
import unicodedata
from dataclasses import dataclass

from app.config import settings
from app.services.llm import chat

logger = logging.getLogger(__name__)

_PROMPT_SYSTEME = (
    "Tu es un juge d'équivalence de questions. "
    "Réponds uniquement par OUI si les deux questions expriment exactement la même demande, "
    "ou NON dans tous les autres cas (nuance, condition supplémentaire, négation, "
    "chiffre différent, périmètre différent, etc.)."
)

# In follow-up mode, question A is a thread not a single question — the standard prompt got refusals by format artifact.
_PROMPT_SYSTEME_SUIVI = (
    "Tu es un juge d'équivalence de questions. "
    "La question A est un fil de discussion : les premières lignes sont le contexte des "
    "échanges précédents, et la DERNIÈRE ligne est la demande réellement posée. "
    "Réponds uniquement par OUI si cette dernière ligne, comprise dans son contexte, "
    "exprime exactement la même demande que la question B, "
    "ou NON dans tous les autres cas (nuance, condition supplémentaire, négation, "
    "chiffre différent, périmètre différent, etc.). "
    "Le contexte sert uniquement à lever les références implicites de la dernière ligne "
    "(« et pour… », « dans ce cas… », pronoms) ; ne juge pas les tours précédents."
)


@dataclass(frozen=True)
class Decision:
    """`court_circuit` distinguishes a no-call OUI from a judged OUI — same outcome, different audit value. `erreur`"""

    verdict: bool
    court_circuit: bool = False
    modele: str | None = None
    erreur: str | None = None


def _normaliser(q: str) -> str:
    """Normalize case, punctuation, whitespace. NFC composes, does not strip accents — « depense » and « dépense »"""
    q = unicodedata.normalize("NFC", q).lower()
    q = re.sub(r"[^\w\s]", " ", q)
    return re.sub(r"\s+", " ", q).strip()


def statuer(question_posee: str, question_indexee: str, *, est_suivi: bool = False) -> Decision:
    """Decide if the question asked calls exactly the same answer as the indexed question. In follow-up mode"""
    # Short-circuit disabled in follow-up mode: comparing a full thread to a single question is meaningless.
    if not est_suivi and _normaliser(question_posee) == _normaliser(question_indexee):
        logger.debug("Garde : répétition exacte → OUI (sans appel LLM)")
        return Decision(verdict=True, court_circuit=True)

    modele = settings.albert_garde_model_name or settings.albert_llm_model_name
    messages = [
        {"role": "system", "content": _PROMPT_SYSTEME_SUIVI if est_suivi else _PROMPT_SYSTEME},
        {
            "role": "user",
            "content": f"Question A : {question_posee}\nQuestion B : {question_indexee}",
        },
    ]
    try:
        verdict = chat(messages, temperature=0, max_tokens=20, model=modele)
        approuve = verdict.strip().upper() == "OUI"
        logger.debug("Garde : %s", "OUI" if approuve else "NON")
        return Decision(verdict=approuve, modele=modele)
    except Exception as exc:
        logger.warning("Garde inaccessible, refus par défaut : %s", exc)
        return Decision(verdict=False, modele=modele, erreur=str(exc)[:500])


def approuver(question_posee: str, question_indexee: str, *, est_suivi: bool = False) -> bool:
    """Boolean wrapper around `statuer`, for callers that don't need verdict details (tests, calibration scripts)."""
    return statuer(question_posee, question_indexee, est_suivi=est_suivi).verdict
