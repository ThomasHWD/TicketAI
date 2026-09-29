"""Contextual Retrieval: prefix each chunk with a one-sentence locator before indexing. Best-effort throughout — a"""

import json
import logging
import re

from app.config import settings
from app.services.llm import chat

logger = logging.getLogger(__name__)

SEPARATEUR = "\n\n"

# A locator, not a summary — beyond this the prefix outweighs the chunk in the sparse vector and dilutes the terms that
MAX_CARACTERES_CONTEXTE = 200

# Wider batches lose the numbering and return offset arrays — _lire_locateurs rejects them, so there's no point paying
TAILLE_LOT = 5

# Object and scope of a note are in the first pages; anything beyond adds nothing to a three-sentence synopsis.
MAX_CARACTERES_SYNOPSIS = 12000

MAX_TOKENS_LOT = 600  # TAILLE_LOT × MAX_CARACTERES_CONTEXTE + JSON punctuation

# A 429 from Albert is day-wide — keep hammering would mean 130 guaranteed failures mid-ingestion.
MAX_ECHECS = 3

_PROMPT_SYNOPSIS = """Tu résumes un document de référence interne pour qu'un autre modèle puisse
y situer des extraits.

Rends 2 à 3 phrases : ce qu'est ce document, à qui il s'applique, quelles règles il porte.

Règles :
- Ne dis que ce que le texte affirme. N'ajoute aucun fait, aucune règle, aucune population absente.
- Pas d'introduction ni de titre : uniquement le résumé.
- 600 caractères maximum."""

_PROMPT_CONTEXTE = """Tu situes des extraits d'un document de référence pour un moteur de
recherche interne.

On te donne un résumé du document et des extraits numérotés. Pour chaque extrait, écris UNE
phrase qui dit de quoi il parle : à quelle règle ou à quel dispositif il se rattache, et à qui
il s'applique. Cette phrase sera préfixée à l'extrait avant indexation — elle sert à le
retrouver, pas à le remplacer.

Règles :
- N'ajoute aucun fait absent du résumé ou de l'extrait. Tu situes, tu n'expliques pas.
- Ne reformule pas le contenu de l'extrait : nomme son sujet.
- Quand l'extrait pose une exception, une restriction ou une condition, dis à quelle règle
  générale elle se rattache et qui elle vise.
- 200 caractères maximum par phrase.
- Si un extrait ne se rattache à rien d'identifiable, rends une chaîne vide pour lui.

Réponds uniquement par un tableau JSON de chaînes, sans texte autour ni bloc de code. Le tableau
porte **exactement une chaîne par extrait**, dans l'ordre de la numérotation : un seul extrait
appelle un tableau d'une seule chaîne, cinq extraits en appellent cinq. Un tableau d'une autre
longueur est inexploitable et sera rejeté."""


def texte_indexe(contenu: str, contexte: str | None) -> str:
    """Single definition of "what text was encoded" — imported by both producers and by"""
    if not contexte:
        return contenu
    return f"{contexte}{SEPARATEUR}{contenu}"


def synopsis(texte: str, filename: str = "", description: str = "") -> str:
    """Two or three sentences describing the document — one call, reused across all batches. Filename and"""
    if not settings.contextualisation_active or not texte.strip():
        return ""

    entete = "\n".join(filter(None, [f"Nom du fichier : {filename}" if filename else "",
                                     f"Description : {description}" if description else ""]))
    try:
        resume = chat(
            [
                {"role": "system", "content": _PROMPT_SYNOPSIS},
                {"role": "user", "content": f"{entete}\n\n{texte[:MAX_CARACTERES_SYNOPSIS]}".strip()},
            ],
            temperature=0,
            max_tokens=300,
            timeout=60,
            model=_modele(),
        )
    except Exception as exc:
        logger.warning("synopsis indisponible (%s) — contextualisation sans ancrage documentaire", exc)
        return ""

    return " ".join(resume.split())


def contextualiser(chunks: list[str], resume: str) -> list[str]:
    """One locator per chunk, always len(chunks) — "" for those that couldn't be located. A misaligned list would"""
    if not chunks:
        return []
    if not settings.contextualisation_active:
        return [""] * len(chunks)

    contextes: list[str] = []
    echecs = 0
    for debut in range(0, len(chunks), TAILLE_LOT):
        lot = chunks[debut : debut + TAILLE_LOT]
        if echecs >= MAX_ECHECS:
            contextes += [""] * len(lot)
            continue

        obtenus = _contextualiser_lot(lot, resume)
        echecs = 0 if obtenus else echecs + 1
        contextes += obtenus or [""] * len(lot)

    if echecs >= MAX_ECHECS:
        logger.warning("contextualisation abandonnée après %d lots en échec — chunks indexés bruts", MAX_ECHECS)
    return contextes


def _modele() -> str:
    """Read at call time, not import — Albert quota is per-model, and changing it must not require editing a .py"""
    return settings.albert_contexte_model_name or settings.albert_tag_model_name


def _contextualiser_lot(lot: list[str], resume: str) -> list[str]:
    """Locators for a batch, or [] if nothing exploitable was returned. Expected count is repeated at end of user"""
    numerotes = "\n\n".join(f"[{i + 1}]\n{c}" for i, c in enumerate(lot))
    try:
        brut = chat(
            [
                {"role": "system", "content": _PROMPT_CONTEXTE},
                {
                    "role": "user",
                    "content": (
                        f"Résumé du document :\n{resume or '(indisponible)'}\n\n"
                        f"Extraits à situer ({len(lot)}) :\n{numerotes}\n\n"
                        f"Rends un tableau JSON de {len(lot)} chaîne(s), dans cet ordre."
                    ),
                },
            ],
            temperature=0,
            max_tokens=MAX_TOKENS_LOT,
            timeout=60,
            model=_modele(),
        )
    except Exception as exc:
        logger.warning("contextualisation d'un lot impossible (%s) — chunks indexés bruts", exc)
        return []

    return _lire_locateurs(brut, len(lot))


def _lire_locateurs(brut: str, attendus: int) -> list[str]:
    """Extract exactly `attendus` strings from model output. Wrong-length array → [], not a partial result — a"""
    debut, fin = brut.find("["), brut.rfind("]")
    if debut == -1 or fin <= debut:
        logger.warning("contextualisation : pas de tableau JSON dans %r", brut[:200])
        return []

    try:
        charge = json.loads(brut[debut : fin + 1])
    except json.JSONDecodeError:
        logger.warning("contextualisation : tableau JSON invalide dans %r", brut[:200])
        return []

    if not isinstance(charge, list) or len(charge) != attendus:
        logger.warning(
            "contextualisation : %s locateurs pour %d extraits — lot ignoré",
            len(charge) if isinstance(charge, list) else type(charge).__name__,
            attendus,
        )
        return []

    return [_sans_repere(" ".join(str(valeur or "").split()))[:MAX_CARACTERES_CONTEXTE] for valeur in charge]


# The extracts are numbered « [k] » in the prompt; the model echoes it (« [1] : Le forfait… », mistral-small, N≥2,
# 29/09/2026) — it would then be embedded and BM25-indexed as if it were part of the locator.
_REPERE = re.compile(r"^\[\d+\]\s*[:.)\-–—]?\s*")


def _sans_repere(locateur: str) -> str:
    return _REPERE.sub("", locateur)
