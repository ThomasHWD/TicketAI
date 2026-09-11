"""Encodeur BM25 : du texte vers un vecteur creux Qdrant.

Le partage des rôles est le point à comprendre. BM25 se décompose en deux
moitiés : l'**IDF**, qui dépend des statistiques du corpus et change à chaque
insertion, et la **saturation TF**, qui ne dépend que du document courant.

Qdrant calcule l'IDF côté serveur (``Modifier.IDF`` sur le vecteur creux, posé
dans ``services/qdrant.py``). Ce module ne produit donc que la seconde moitié :
des indices de tokens et leurs poids TF. C'est exactement le découpage que fait
``fastembed`` en interne, sans la dépendance ni le téléchargement au runtime.

Ce qui est délégué et ce qui ne l'est pas : la radicalisation vient de
``snowballstemmer``, l'implémentation de référence de Snowball — la même famille
d'algorithmes que Lucene. Rien ici n'est un algorithme maison.
"""

import unicodedata
from functools import lru_cache

import regex
import xxhash

# Paramètres BM25 standards. `AVG_LEN` est une constante assumée : un client ne
# connaît pas la longueur moyenne du corpus, et l'interroger à chaque encodage
# coûterait un aller-retour par texte. Même choix que `fastembed`.
K1 = 1.2
B = 0.75
AVG_LEN = 40  # en tokens — ordre de grandeur d'une question, pas d'un document

# Lettres et chiffres, la ponctuation et les symboles écartés d'emblée.
_MOT = regex.compile(r"[\p{L}\p{N}][\p{L}\p{N}]*", regex.UNICODE)

# …mais **pas les chiffres isolés**. Un nombre d'au moins deux chiffres est une
# valeur (« 35 » heures, « 50 » %, « 31 » mai) et discrimine ; un chiffre seul est
# du bruit, et il arrive surtout comme débris de découpage — « L3262-1 » produit
# `1`, « 0,25 » produit `0`.
#
# Mesuré hors ligne sur les 613 points du corpus, trois tokenisations comparées
# (11/09/2026). Écarter les nombres nus fait manquer des valeurs : « 35 heures par
# semaine » notait 3,83/terme contre un bruit à 3,35, soit une séparation de 1,14× ;
# en gardant « 35 » elle passe à 5,43 contre 2,18, soit 2,5×. « 50 % de
# l'abonnement » remonte la bonne réponse du rang 2 au rang 1. Mais tout garder
# régresse sur « article L3262-1 », où le `1` hisse un passage sans rapport au
# rang 2. D'où ce seuil à deux chiffres : meilleur ou égal sur les cinq requêtes
# testées, sans la régression.
LONGUEUR_MIN_NOMBRE = 2


def _est_bruit_numerique(mot: str) -> bool:
    return mot.isdigit() and len(mot) < LONGUEUR_MIN_NOMBRE


# Élisions françaises. Sans ce traitement, « l'abonnement » produit les tokens
# `l` et `abonnement` : le premier est du bruit pur, et il est fréquent au point
# de peser dans l'index. Le découpage naïf sur les apostrophes est le défaut le
# plus courant des tokeniseurs appliqués au français.
_ELISIONS = frozenset(["l", "d", "j", "n", "s", "t", "c", "m", "qu", "lorsqu", "puisqu", "quoiqu", "jusqu"])

# Mots-outils français. Ils ne discriminent rien et, sans IDF côté requête, ils
# domineraient le score par leur seule fréquence.
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
    """Chargé paresseusement : importer snowballstemmer coûte au démarrage."""
    import snowballstemmer

    return snowballstemmer.stemmer("french")


def _sans_accents(texte: str) -> str:
    """Repli des diacritiques : « télétravail » et « teletravail » doivent coïncider.

    Contrairement à `_normaliser` du garde (`services/garde_cache.py`), qui
    préserve délibérément les accents parce qu'il compare deux questions au
    caractère près, l'indexation lexicale a tout intérêt à les effacer : une
    faute d'accent dans une question posée ne doit pas manquer le document.
    """
    return "".join(c for c in unicodedata.normalize("NFD", texte) if unicodedata.category(c) != "Mn")


def tokeniser(texte: str) -> list[str]:
    """Texte → radicaux signifiants, élisions et mots-outils écartés."""
    brut = _sans_accents(texte.lower())
    mots = [
        m for m in _MOT.findall(brut) if m not in _ELISIONS and m not in _STOP_WORDS and not _est_bruit_numerique(m)
    ]
    if not mots:
        return []
    return [r for r in _radicaliseur().stemWords(mots) if r]


def index_du_token(token: str) -> int:
    """Indice stable pour Qdrant.

    `xxhash` et non le `hash()` de Python : ce dernier est randomisé par
    `PYTHONHASHSEED` à chaque démarrage de processus. Un index écrit par le
    worker d'ingestion ne serait alors plus retrouvable par l'API — une panne
    silencieuse, qui ne se manifesterait que par une recherche lexicale muette.
    """
    return xxhash.xxh32_intdigest(token)


def encoder(texte: str, *, est_requete: bool = False) -> dict[str, list]:
    """Vecteur creux BM25, au format attendu par `SparseVector`.

    `est_requete` distingue les deux côtés de BM25 : un **document** est pondéré
    par la saturation TF (un mot répété dix fois ne vaut pas dix fois un mot vu
    une fois, et un document long est pénalisé), tandis qu'une **requête** ne
    porte aucune pondération — ses termes valent 1, l'IDF de Qdrant faisant le
    reste. C'est ce qui donne enfin un sens au paramètre `is_query` de
    `embed_texts`, accepté mais ignoré jusqu'ici.
    """
    radicaux = tokeniser(texte)
    if not radicaux:
        return {"indices": [], "values": []}

    frequences: dict[int, int] = {}
    for radical in radicaux:
        indice = index_du_token(radical)
        frequences[indice] = frequences.get(indice, 0) + 1

    if est_requete:
        return {"indices": list(frequences), "values": [1.0] * len(frequences)}

    # Saturation BM25 : f·(k1+1) / (f + k1·(1 − b + b·|D|/avgdl))
    longueur = len(radicaux)
    norme = K1 * (1 - B + B * longueur / AVG_LEN)
    return {
        "indices": list(frequences),
        "values": [f * (K1 + 1) / (f + norme) for f in frequences.values()],
    }
