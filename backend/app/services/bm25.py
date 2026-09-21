"""BM25 sparse encoder: produces TF weights only — Qdrant computes IDF server-side via Modifier.IDF."""

import unicodedata
from functools import lru_cache

import regex
import xxhash

K1 = 1.2
# AVG_LEN stays a constant: querying corpus stats per encode would cost one round-trip each time.

# ⚠️ Calibrated pair (measured doc-chunk mean) — changing either invalidates stored sparse vectors; re-encode with
B = 0.70
AVG_LEN = 96  # BM25 tokens — measured mean of document chunks

_MOT = regex.compile(r"[\p{L}\p{N}][\p{L}\p{N}]*", regex.UNICODE)

# Two-char minimum: single digits are tokenization artifacts (L3262-1 → `1`); multi-digit numbers carry meaning.
LONGUEUR_MIN_NOMBRE = 2


def _est_bruit_numerique(mot: str) -> bool:
    return mot.isdigit() and len(mot) < LONGUEUR_MIN_NOMBRE


# Position-based elision removal, not letter-set — preserves meaningful single-letter tokens (disque C, vitamine D).
_ELISION = regex.compile(r"\b(?:lorsqu|puisqu|quoiqu|jusqu|qu|[ldjnstcm])['']")

# Stopwords don't discriminate and, without query-side IDF, would dominate scores by frequency alone.
_STOP_WORDS = frozenset(
    """
    a ai aie aient aies ait alors as au aucun aucune aujourd aura aurai auraient aurais aurait
    auras aurez auriez aurions aurons auront aussi autre autres aux avaient avais avait avant
    avec avez aviez avions avoir avons ayant ayez ayons beaucoup bien car ce ceci cela celle
    celles celui cependant certain certaine certaines certains ces cet cette ceux chaque chez ci
    comme comment dans de dedans dehors depuis des deux doit doivent donc dont du elle elles en
    encore entre es est et eta etaient etais etait etant etc ete etes etre eu eux fait faire fais
    faisait fait fois font furent fut hors ici il ils je juste la le les leur leurs lui ma mais
    me meme memes mes mien mienne miens moi moins mon mot ne ni nos notre nous nulle on ont ou
    oui par parce pas peu peut peuvent plupart plus plutot pour pourquoi puis qu quand que quel
    quelle quelles quels qui quoi sa sans se sera serai seraient serais serait seras serez seriez
    serions serons seront ses si sien sienne siens soi soient sois soit sommes son sont soyez
    soyons suis sur ta te tes tien tienne tiens toi ton tous tout toute toutes tu un une vos
    votre vous y etaient etions etiez
    """.split()
)


@lru_cache(maxsize=1)
def _radicaliseur():
    """Lazy-loaded: importing snowballstemmer has a measurable startup cost."""
    import snowballstemmer

    return snowballstemmer.stemmer("french")


def _sans_accents(texte: str) -> str:
    """Strip diacritics for indexing — a typo shouldn't miss a document. Unlike `_normaliser` in garde_cache"""
    return "".join(c for c in unicodedata.normalize("NFD", texte) if unicodedata.category(c) != "Mn")


def tokeniser(texte: str) -> list[str]:
    """Text → meaningful stems. Elision stripped before tokenization (positional, before word boundaries are"""
    brut = _ELISION.sub("", _sans_accents(texte.lower()))
    mots = [m for m in _MOT.findall(brut) if m not in _STOP_WORDS and not _est_bruit_numerique(m)]
    if not mots:
        return []
    return [r for r in _radicaliseur().stemWords(mots) if r]


def index_du_token(token: str) -> int:
    """Stable index for Qdrant. xxhash, not Python's `hash()` — PYTHONHASHSEED is randomized per process, making"""
    return xxhash.xxh32_intdigest(token)


def encoder(texte: str, *, est_requete: bool = False) -> dict[str, list]:
    """BM25 sparse vector. `est_requete=True` emits uniform weights (1.0) — the query side needs no TF saturation"""
    radicaux = tokeniser(texte)
    if not radicaux:
        return {"indices": [], "values": []}

    frequences: dict[int, int] = {}
    for radical in radicaux:
        indice = index_du_token(radical)
        frequences[indice] = frequences.get(indice, 0) + 1

    if est_requete:
        return {"indices": list(frequences), "values": [1.0] * len(frequences)}

    longueur = len(radicaux)
    norme = K1 * (1 - B + B * longueur / AVG_LEN)
    return {
        "indices": list(frequences),
        "values": [f * (K1 + 1) / (f + norme) for f in frequences.values()],
    }
