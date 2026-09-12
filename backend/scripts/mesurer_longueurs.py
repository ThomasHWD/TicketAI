"""Mesure les longueurs réelles du corpus indexé, pour recalibrer `AVG_LEN`/`B`.

`bm25.py` fixe ces deux constantes ensemble sous une contrainte : ramener
`AVG_LEN` sur la moyenne réelle des chunks de documents **sans** déplacer
l'échelle des points-réponses, puisque c'est elle que seuille
`SEUIL_LEXICAL_PAR_TERME`. Ce script refait la mesure et résout `B`.

À relancer quand la part des points-réponses dans le corpus devient
significative, ou après tout changement de la tokenisation (qui déplace le
nombre de tokens BM25 par texte, donc la moyenne).

Usage :
    PYTHONPATH=. python scripts/mesurer_longueurs.py

Lecture seule sur Qdrant. Aucun appel Albert.

⚠️ Appliquer le résultat **invalide les vecteurs déjà écrits** : la saturation TF
est figée à l'écriture, contrairement à l'IDF que Qdrant recalcule. Réindexer
ensuite avec `scripts/reinitialiser_index.py`.
"""

import os
import statistics
import sys

os.environ.setdefault("QDRANT_HOST", "localhost")
os.environ.setdefault("QDRANT_PORT", "6335")

from app.services.bm25 import AVG_LEN, K1, B, tokeniser  # noqa: E402
from app.services.qdrant import COLLECTION_NAME, client  # noqa: E402

# Longueur de référence d'une question posée, en tokens BM25. C'est le point que
# le recalibrage doit laisser immobile.
LONGUEUR_QUESTION = 5


def poids_tf(longueur: int, *, b: float, avg_len: float, frequence: int = 1) -> float:
    """Saturation BM25 d'un terme vu `frequence` fois dans un texte de `longueur`."""
    return frequence * (K1 + 1) / (frequence + K1 * (1 - b + b * longueur / avg_len))


def parcourir_points() -> tuple[list[int], list[int]]:
    """Longueurs en tokens BM25, séparées par population.

    Un point-réponse est indexé sous sa **question** (`question_indexee`), pas
    sous le contenu de la réponse : c'est ce texte-là qu'il faut mesurer, sinon
    on mesure une population qui n'existe pas dans l'index.
    """
    documents: list[int] = []
    reponses: list[int] = []
    offset = None
    while True:
        lot, offset = client.scroll(COLLECTION_NAME, limit=500, offset=offset, with_payload=True, with_vectors=False)
        for point in lot:
            charge = point.payload or {}
            if charge.get("reponse_id"):
                texte = charge.get("question_indexee") or charge.get("contenu") or ""
                reponses.append(len(tokeniser(texte)))
            else:
                documents.append(len(tokeniser(charge.get("contenu") or "")))
        if offset is None:
            return documents, reponses


def decrire(nom: str, valeurs: list[int]) -> None:
    if not valeurs:
        print(f"  {nom:22s} aucun point")
        return
    ecart = statistics.pstdev(valeurs) if len(valeurs) > 1 else 0.0
    moyenne = statistics.mean(valeurs)
    # Le coefficient de variation dit si `B` a encore un travail utile à faire
    # *à l'intérieur* de la population : proche de zéro, la normalisation par la
    # longueur n'y sépare plus rien et n'agit qu'entre populations.
    cv = ecart / moyenne if moyenne else 0.0
    print(
        f"  {nom:22s} n={len(valeurs):4d}  moyenne={moyenne:6.1f}  "
        f"mediane={statistics.median(valeurs):6.1f}  ecart-type={ecart:5.1f}  CV={cv:.2f}"
    )


def main() -> int:
    if not client.collection_exists(COLLECTION_NAME):
        print(f"collection « {COLLECTION_NAME} » absente", file=sys.stderr)
        return 1

    documents, reponses = parcourir_points()
    print(f"collection « {COLLECTION_NAME} » — {len(documents) + len(reponses)} points")
    decrire("chunks documents", documents)
    decrire("points-reponses", reponses)

    if not documents:
        print("\naucun chunk de document : rien à recalibrer", file=sys.stderr)
        return 1

    avg_len = round(statistics.mean(documents))
    cible = poids_tf(LONGUEUR_QUESTION, b=B, avg_len=AVG_LEN)

    # On veut `b` tel que poids_tf(LONGUEUR_QUESTION, b, avg_len) == cible.
    # En posant r = LONGUEUR_QUESTION / avg_len, la saturation à f=1 s'écrit
    #   2,2 / (1 + K1·(1 − b + b·r))
    # d'où, en isolant b :
    #   b = (1 − (2,2/cible − 1)/K1) / (1 − r)
    ratio = LONGUEUR_QUESTION / avg_len
    b = (1 - ((K1 + 1) / cible - 1) / K1) / (1 - ratio)

    print(f"\nactuel    AVG_LEN={AVG_LEN:5d}  B={B:.3f}")
    print(f"propose   AVG_LEN={avg_len:5d}  B={b:.3f}")
    print(
        f"\n  poids TF d'une question de {LONGUEUR_QUESTION} tokens : "
        f"{cible:.3f} -> {poids_tf(LONGUEUR_QUESTION, b=b, avg_len=avg_len):.3f}  (doit rester immobile)"
    )
    avant = cible / poids_tf(avg_len, b=B, avg_len=AVG_LEN)
    apres = poids_tf(LONGUEUR_QUESTION, b=b, avg_len=avg_len) / poids_tf(avg_len, b=b, avg_len=avg_len)
    print(f"  ecart question / chunk moyen : {avant:.2f}x -> {apres:.2f}x")
    print("\nreindexer apres application : PYTHONPATH=. python scripts/reinitialiser_index.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
