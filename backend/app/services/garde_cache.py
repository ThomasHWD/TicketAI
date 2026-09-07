"""Garde du cache canonique : vérifie que la question posée exprime exactement
la même demande que la question indexée avant de servir une réponse sans revue humaine.

Conservateur par construction : toute réponse autre que "OUI" explicite → refus.
Erreur LLM, timeout, réponse ambiguë → refus.
"""

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

# En mode suivi, la question A n'est pas une question mais un fil : les tours
# précédents concaténés, la précision en dernière ligne. Soumis au prompt
# ci-dessus, un fil de deux questions ne peut pratiquement jamais « exprimer
# exactement la même demande » qu'une question unique — le garde refusait alors
# par artefact de format plutôt que par jugement. Ce prompt lui dit où est la
# demande et à quoi sert le reste.
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
    """Verdict du garde, avec de quoi le journaliser et l'auditer.

    `court_circuit` distingue un OUI rendu sans appel LLM d'un OUI du juge :
    les deux servent la réponse, mais ils n'ont pas la même valeur de preuve.
    `erreur` distingue un NON jugé d'un NON par défaut faute d'avoir pu joindre
    Albert — ce dernier ne doit pas être compté comme un refus du juge.
    """

    verdict: bool
    court_circuit: bool = False
    modele: str | None = None
    erreur: str | None = None


def _normaliser(q: str) -> str:
    """Normalise casse, ponctuation et espaces. **Ne retire pas les accents** :
    NFC compose les caractères, il ne les dépouille pas. « depense » et
    « dépense » restent donc distincts et passent par le juge.
    """
    q = unicodedata.normalize("NFC", q).lower()
    q = re.sub(r"[^\w\s]", " ", q)
    return re.sub(r"\s+", " ", q).strip()


def statuer(question_posee: str, question_indexee: str, *, est_suivi: bool = False) -> Decision:
    """Décide si la question posée appelle exactement la même réponse que la question indexée.

    En mode suivi, `question_posee` est le fil concaténé et non la seule
    précision : une précision elliptique (« et pour la médecine de prévention ? »)
    ne veut rien dire hors de son fil.
    """
    # Court-circuit réservé au hors-suivi. Comparer typographiquement un fil
    # entier à une question unique n'a pas de sens ; ne comparer que sa dernière
    # ligne reviendrait à servir une réponse canonique en ayant jeté le contexte
    # qui la rend sûre.
    if not est_suivi and _normaliser(question_posee) == _normaliser(question_indexee):
        logger.info("Garde : répétition exacte → OUI (sans appel LLM)")
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
        logger.info("Garde : %s", "OUI" if approuve else "NON")
        return Decision(verdict=approuve, modele=modele)
    except Exception as exc:
        logger.warning("Garde inaccessible, refus par défaut : %s", exc)
        return Decision(verdict=False, modele=modele, erreur=str(exc)[:500])


def approuver(question_posee: str, question_indexee: str, *, est_suivi: bool = False) -> bool:
    """Retourne True si et seulement si les deux questions expriment exactement la même demande.

    Enveloppe booléenne de `statuer`, pour les appelants qui n'ont que faire du
    détail du verdict (tests, scripts de calibration).
    """
    return statuer(question_posee, question_indexee, est_suivi=est_suivi).verdict
