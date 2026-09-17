"""Situe chaque chunk dans son document avant de l'indexer (Contextual Retrieval).

Un chunk est vectorisé **isolé** : ni le dense ni le creux ne portent ce que le
document dit autour de lui. « Les alternants n'en bénéficient pas » ne contient
pas le mot « télétravail » : aucune recherche sur le télétravail ne le ramène, et
la réponse énonce la règle générale sans son exception.

Le rattrapage consiste à préfixer chaque chunk d'une phrase qui le *situe* — de
quelle règle il relève, à qui elle s'applique — et à indexer ce texte-là. La
phrase est un **locateur**, pas un résumé : elle sert à retrouver le passage,
jamais à le remplacer.

Économie du procédé. La recette d'origine remet le document entier à chaque
chunk : sur ce corpus (578 chunks) ≈ 5,8 M jetons d'entrée, pour un quota Albert
de 1 280 000 jetons/jour **et** 1 000 requêtes/jour, l'un comme l'autre attachés
au modèle. On paie donc un **synopsis** une fois (1 appel), puis on contextualise
par **lots de 5** : ≈ 2 300 jetons par appel, ≈ 130 appels pour le même corpus.

**Tout est best-effort.** Panne réseau, JSON illisible, tableau de longueur
inattendue : la fonction rend ``""`` et l'ingestion retombe très exactement sur
son comportement d'avant ce module. Une contextualisation ratée dégrade le
rappel ; elle ne doit jamais faire échouer une ingestion par ailleurs réussie.
"""

import json
import logging

from app.config import settings
from app.services.llm import chat

logger = logging.getLogger(__name__)

SEPARATEUR = "\n\n"

# Un locateur, pas un résumé. Au-delà, le préfixe pèse plus lourd que le passage
# dans le vecteur creux et dilue les termes qui font justement trouver le chunk.
MAX_CARACTERES_CONTEXTE = 200

# Chunks par appel. Plus large, le modèle perd le fil de la numérotation et rend
# des tableaux décalés — que `_lire_locateurs` jette, donc autant ne pas les payer.
TAILLE_LOT = 5

# Troncature du document soumis au synopsis (≈ 3 000 jetons). L'objet et le
# périmètre d'une note se lisent dans ses premières pages ; la suite n'ajoute
# rien à un texte qui doit tenir en trois phrases.
MAX_CARACTERES_SYNOPSIS = 12000

# Jetons de sortie pour un lot : TAILLE_LOT × MAX_CARACTERES_CONTEXTE, plus la
# ponctuation JSON.
MAX_TOKENS_LOT = 600

# Lots consécutifs en échec avant d'abandonner le document. Un 429 d'Albert vaut
# pour la journée entière : insister ferait attendre 130 fois le réseau pour 130
# échecs certains, au milieu d'une ingestion. Même discipline que le `MAX_ECHECS`
# de `workers/reverification.py`.
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

Réponds uniquement par un tableau JSON de chaînes, un par extrait et dans le même ordre, sans
texte autour ni bloc de code :
["…", "…"]"""


def texte_indexe(contenu: str, contexte: str | None) -> str:
    """Le texte réellement encodé pour un chunk de document.

    Définition **unique**, importée par les deux producteurs
    (``workers/ingestion.py``, ``workers/document_update.py``) et par
    ``scripts/reencoder_vecteurs_creux.py``. Si ces trois-là divergeaient, la
    prochaine recalibration BM25 réécrirait les vecteurs creux à partir d'un
    autre texte que celui indexé — silencieusement, puisque rien ne lève.

    ``contexte`` vide rend ``contenu`` **inchangé**, caractère pour caractère :
    c'est ce qui fait que les points écrits avant ce module restent exacts.
    """
    if not contexte:
        return contenu
    return f"{contexte}{SEPARATEUR}{contenu}"


def synopsis(texte: str, filename: str = "", description: str = "") -> str:
    """Deux ou trois phrases sur ce qu'est ce document — un seul appel.

    C'est l'ancrage que ``contextualiser`` réutilise sur chaque lot : sans lui,
    situer un passage demanderait de renvoyer le document entier à chaque fois.

    Le nom du fichier et la description sont joints parce qu'ils portent souvent
    le périmètre que le corps du texte tait (« charte_teletravail_2026.pdf »).

    Rend ``""`` sur n'importe quelle panne : ``contextualiser`` sait travailler
    sans ancrage, et le prompt lui dit de rendre une chaîne vide pour tout
    extrait qu'il ne parvient pas à situer.
    """
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
    """Un locateur par chunk, dans l'ordre — ``""`` pour ceux qu'on n'a pas su situer.

    La liste rendue fait **toujours** la longueur de ``chunks`` : l'appelant
    l'apparie par position, et un décalage préfixerait chaque passage du sujet
    de son voisin. C'est le seul mode d'échec qui serait pire que l'absence de
    contexte, parce qu'il ferait trouver le mauvais chunk au lieu de n'en
    trouver aucun.

    Un lot qui échoue ne condamne que ses cinq chunks. Trois lots consécutifs en
    échec abandonnent le document : voir ``MAX_ECHECS``.
    """
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
    """Le modèle du contexte, avec repli sur celui des tags.

    Lu à l'appel et non à l'import, comme ``albert_garde_model_name`` : le quota
    Albert est compté **par modèle**, et il faut pouvoir déplacer celui-ci sans
    toucher un ``.py`` — ce qui relancerait uvicorn et les workers en pleine
    ingestion.
    """
    return settings.albert_contexte_model_name or settings.albert_tag_model_name


def _contextualiser_lot(lot: list[str], resume: str) -> list[str]:
    """Les locateurs d'un lot, ou ``[]`` si ce lot n'a rien donné d'exploitable."""
    numerotes = "\n\n".join(f"[{i + 1}]\n{c}" for i, c in enumerate(lot))
    try:
        brut = chat(
            [
                {"role": "system", "content": _PROMPT_CONTEXTE},
                {
                    "role": "user",
                    "content": (
                        f"Résumé du document :\n{resume or '(indisponible)'}\n\n"
                        f"Extraits à situer ({len(lot)}) :\n{numerotes}"
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
    """Extrait un tableau de ``attendus`` chaînes d'une sortie de modèle.

    Tolère l'encadrement en bloc de code et le bavardage autour du tableau, que
    les modèles produisent malgré la consigne. Toute autre forme rend ``[]`` :
    ici, contrairement à ``_lire_verdict``, il n'existe pas de repli prudent — un
    tableau de la mauvaise longueur n'est pas une hésitation qu'on pourrait
    arrondir, c'est un appariement dont on ne sait plus rien.
    """
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

    return [" ".join(str(valeur or "").split())[:MAX_CARACTERES_CONTEXTE] for valeur in charge]
