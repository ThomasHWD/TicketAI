"""Le rappel de la ré-vérification, mesuré contre le vrai index.

`scripts/test_reverification_reel.py` teste le **juge** (dernier étage) sur des
unités fabriquées à la main. Il ne dit rien de l'étage qui le précède : le
rappel. Or c'est le seul endroit de ce pipeline que BM25 pouvait déplacer —
`_voisines` appelle `embed_texts`, dont la moitié creuse n'était plus vide
depuis le 11/09/2026. Un juge parfait sur des candidates jamais rappelées ne
prouve rien.

Le protocole : on prend le corpus de test `test-avantages-v1.txt` et ses 14
réponses canoniques (domaine TEST), on fabrique une v2 en modifiant **trois
valeurs chiffrées** dans trois sections différentes, et on vérifie que
`rassembler_candidates` remonte les réponses qui portent ces chiffres.

Les citantes ne jouent pas ici : aucune de ces réponses ne cite le document
(elles ont été validées à la main). Tout ce qui remonte passe donc par
`_voisines`, c'est-à-dire par l'embedding — exactement la surface visée.

Coût : un appel d'embedding Albert (les unités tiennent dans un lot), **zéro
appel au juge**. Ajouter `--juger` pour enchaîner le funnel complet, qui coûte
alors un rerank + un chat par candidate.

Usage :
    PYTHONPATH=. python scripts/test_reverification_rappel_reel.py
    PYTHONPATH=. python scripts/test_reverification_rappel_reel.py --juger
"""

import argparse
import os

os.environ.setdefault("QDRANT_HOST", "localhost")
os.environ.setdefault("QDRANT_PORT", "6335")
os.environ.setdefault("POSTGRES_HOST", "localhost")
os.environ.setdefault("POSTGRES_PORT", "5433")

from app.database import SessionLocal  # noqa: E402
from app.services.diff import unites_de_changement  # noqa: E402
from app.services.reverification_candidates import rassembler_candidates  # noqa: E402
from app.services.reverification_scoring import juger, unites_pertinentes  # noqa: E402

DOC_ID = "a0174eb3-8604-4cf4-bddf-d9009b7dd23a"
DOMAINE = "TEST"
CHEMIN_V1 = f"/app/storage/{DOC_ID}/v1/test-avantages-v1.txt"

# Trois valeurs, trois sections éloignées. Chacune est portée par une réponse
# canonique identifiée : si le rappel les manque, il ne rappelle rien d'utile.
MODIFICATIONS = [
    ("d'une valeur faciale de neuf euros (9,00 €)",
     "d'une valeur faciale de dix euros (10,00 €)"),
    ("dans la limite de deux jours ouvrés par semaine",
     "dans la limite de trois jours ouvrés par semaine"),
    ("indemnité kilométrique de zéro euro vingt-cinq (0,25 €) par kilomètre",
     "indemnité kilométrique de zéro euro trente (0,30 €) par kilomètre"),
]

# Ce que le rappel doit remonter, par fragment de question.
ATTENDUES = [
    "valeur faciale du titre-restaurant",
    "jours de télétravail par semaine",
    "vélo",
]


def charger_v1() -> str:
    with open(CHEMIN_V1, encoding="utf-8") as f:
        return f.read()


def main() -> None:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--juger", action="store_true", help="enchaîner rerank + juge sur les candidates")
    args = parser.parse_args()

    v1 = charger_v1()
    v2 = v1
    for avant, apres in MODIFICATIONS:
        if avant not in v2:
            raise SystemExit(f"Fragment introuvable dans la v1, corpus modifié ? → {avant!r}")
        v2 = v2.replace(avant, apres)

    unites = unites_de_changement(v1, v2)
    print(f"{len(unites)} unité(s) de changement pour {len(MODIFICATIONS)} modification(s)\n")
    for u in unites:
        print(f"  [{u.sens}] {(u.apres or u.avant or '')[:100]}…")
    print()

    db = SessionLocal()
    try:
        candidates = rassembler_candidates(db, DOC_ID, DOMAINE, unites, indices_disparus=set())
        print(f"{len(candidates)} candidate(s) rappelée(s) :")
        for c in candidates:
            marque = "citante" if c.citante else "voisine"
            print(f"  [{marque}] {c.question[:80]}")
        print()

        questions = " | ".join(c.question.lower() for c in candidates)
        manquees = [a for a in ATTENDUES if a.lower() not in questions]
        print(f"RAPPEL : {len(ATTENDUES) - len(manquees)}/{len(ATTENDUES)} attendues remontées")
        for m in manquees:
            print(f"  ❌ manquée : « {m} »")
        if not manquees:
            print("  ✅ les trois réponses portant les valeurs modifiées sont rappelées")

        if not args.juger:
            print("\n(--juger pour enchaîner rerank + juge)")
            return

        print(f"\n{'═' * 72}\nFUNNEL COMPLET ({len(candidates)} rerank + jusqu'à autant de chat)\n{'═' * 72}")
        for c in candidates:
            retenues, fiable = unites_pertinentes(c.question, unites)
            if not retenues and fiable:
                print(f"  ⏭  {c.question[:60]} → aucune unité pertinente, non jugée")
                continue
            verdict, justification = juger(c.question, c.reponse.contenu, retenues or unites)
            print(f"  {verdict:<10} {c.question[:60]}")
            if verdict != "INTACTE":
                print(f"             {justification[:140]}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
