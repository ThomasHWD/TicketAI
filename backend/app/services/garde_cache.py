"""Garde du cache canonique : vérifie que la question posée exprime exactement
la même demande que la question indexée avant de servir une réponse sans revue humaine.

Conservateur par construction : toute réponse autre que "OUI" explicite → refus.
Erreur LLM, timeout, réponse ambiguë → refus.
"""

import logging
import re
import unicodedata

from app.config import settings
from app.services.llm import chat

logger = logging.getLogger(__name__)

_PROMPT_SYSTEME = (
    "Tu es un juge d'équivalence de questions. "
    "Réponds uniquement par OUI si les deux questions expriment exactement la même demande, "
    "ou NON dans tous les autres cas (nuance, condition supplémentaire, négation, "
    "chiffre différent, périmètre différent, etc.)."
)


def _normaliser(q: str) -> str:
    q = unicodedata.normalize("NFC", q).lower()
    q = re.sub(r"[^\w\s]", " ", q)
    return re.sub(r"\s+", " ", q).strip()


def approuver(question_posee: str, question_indexee: str) -> bool:
    """Retourne True si et seulement si les deux questions expriment exactement la même demande.

    Court-circuit sans appel LLM si les questions sont typographiquement identiques
    (casse, accents, ponctuation, espaces).
    """
    if _normaliser(question_posee) == _normaliser(question_indexee):
        logger.info("Garde : répétition exacte → OUI (sans appel LLM)")
        return True

    modele = settings.albert_garde_model_name or settings.albert_llm_model_name
    messages = [
        {"role": "system", "content": _PROMPT_SYSTEME},
        {
            "role": "user",
            "content": f"Question A : {question_posee}\nQuestion B : {question_indexee}",
        },
    ]
    try:
        verdict = chat(messages, temperature=0, max_tokens=20, model=modele)
        approuve = verdict.strip().upper() == "OUI"
        logger.info("Garde : %s", "OUI" if approuve else "NON")
        return approuve
    except Exception as exc:
        logger.warning("Garde inaccessible, refus par défaut : %s", exc)
        return False
