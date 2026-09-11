"""Mesure ce que la porte lexicale apporte, sur le corpus réel.

Le cas d'école de BM25 est le terme que le modèle d'embedding ne connaît pas :
référence d'article, sigle, nom propre, montant. Le cosinus y est médiocre, le
recouvrement de mots parfait. Ce script le vérifie plutôt que de le supposer.

Pour chaque requête, il compare **la même recherche** vue de deux façons :
  - dense seul, comme avant BM25 ;
  - disjonction cosinus / lexical, comme aujourd'hui.
Une seule recherche par requête, donc un seul appel Albert : les deux verdicts
se déduisent des scores renvoyés.

Usage : PYTHONPATH=. python scripts/test_lexical_reel.py
"""

import os

os.environ.setdefault("QDRANT_HOST", "localhost")
os.environ.setdefault("QDRANT_PORT", "6335")
os.environ.setdefault("POSTGRES_HOST", "localhost")
os.environ.setdefault("POSTGRES_PORT", "5433")

from app.config import settings  # noqa: E402
from app.services.bm25 import tokeniser  # noqa: E402
from app.services.search import search_hybrid  # noqa: E402

DOMAINE = "IT"

# (requête, fragment attendu dans le chunk pertinent)
# Tirées du GUIDE DES AVANTAGES SALARIÉS réellement indexé.
CAS = [
    ("L3262-1", "titre-restaurant"),
    ("article L1222-9", "télétravail"),
    ("L3261-2", "transport"),
    ("L911-1", "prévoyance"),
    ("carte Swile", "swile"),
    ("valeur faciale 9 euros", "faciale"),
    ("titres-restaurant alternant stagiaire", "alternant"),
]


def rang_du_bon_chunk(resultats: list[dict], fragment: str) -> int | None:
    for i, c in enumerate(resultats):
        if fragment.lower() in (c.get("contenu") or "").lower():
            return i
    return None


def main() -> None:
    seuil = settings.seuil_cosinus
    lexical_mini = settings.seuil_lexical_par_terme
    print(f"domaine={DOMAINE} · seuil cosinus={seuil} · porte lexicale ≥ {lexical_mini}/terme\n")

    gagnes = 0
    for requete, fragment in CAS:
        resultats = search_hybrid(requete, DOMAINE, top_k=15)
        rang = rang_du_bon_chunk(resultats, fragment)
        if rang is None:
            print(f"« {requete} » → chunk attendu ABSENT du top-15  (tokens={tokeniser(requete)})")
            print()
            continue

        c = resultats[rang]
        cos, lex = c["score_cosinus"], c["score_lexical"]
        dense_seul = cos >= seuil
        hybride = dense_seul or (lexical_mini > 0 and lex >= lexical_mini)
        if hybride and not dense_seul:
            gagnes += 1

        print(f"« {requete} »   tokens={tokeniser(requete)}")
        print(
            f"   rang {rang + 1}/15 · cos={cos:.4f} · lexical={lex:.3f}/terme"
            f"   dense seul: {'✓' if dense_seul else '✗'}   hybride: {'✓' if hybride else '✗'}"
            f"{'   ← RATTRAPÉ PAR LE LEXICAL' if hybride and not dense_seul else ''}"
        )
        print()

    print(f"Rattrapés par la porte lexicale : {gagnes}/{len(CAS)}")


if __name__ == "__main__":
    main()
