"""Réécrit les vecteurs creux de la collection, sans toucher au dense.

À lancer après tout changement de `services/bm25.py` — `K1`, `B`, `AVG_LEN`, la
tokenisation, le hachage. La saturation TF est **figée à l'écriture** (seul l'IDF
est recalculé par Qdrant à chaque requête), donc les points déjà indexés portent
encore les poids de l'ancienne formule et deviennent incomparables aux nouveaux.

Pourquoi pas `reinitialiser_index.py` : parce que rien de ce qui change ici ne
concerne le vecteur dense. Rejouer toute l'ingestion rachèterait un embedding
Albert par chunk — 618 points, ~50 requêtes sur un quota de 1 000/jour — pour
réécrire une moitié de vecteur que le client calcule localement et gratuitement.
Ce script ne fait donc qu'un `update_vectors` sur la branche `sparse`.

C'est exact et non destructif : le texte réellement encodé est conservé dans le
payload par les deux producteurs, à l'identique.

  - chunks de documents : ``texte_indexe(payload["contenu"], payload["contexte"])``
    reconstitue exactement le texte passé à `embed_texts` (`workers/ingestion.py`,
    `workers/document_update.py`) — le chunk brut, précédé de son locateur quand
    la contextualisation en a produit un ;
  - points-réponses : ``payload["question_indexee"]`` est le `texte_a_indexer`
    passé à `embed_texts` (`workers/feedback.py`).

Le repli sur ``contenu`` pour un point-réponse couvre les points écrits avant
l'indexation multi-formulations, qui n'ont pas de `question_indexee`.

Usage :
    PYTHONPATH=. python scripts/reencoder_vecteurs_creux.py            # simulation
    PYTHONPATH=. python scripts/reencoder_vecteurs_creux.py --appliquer
"""

import argparse
import os
import sys

os.environ.setdefault("QDRANT_HOST", "localhost")
os.environ.setdefault("QDRANT_PORT", "6335")

from app.services.bm25 import AVG_LEN, K1, B, encoder  # noqa: E402
from app.services.contextualisation import texte_indexe as recomposer  # noqa: E402
from app.services.qdrant import COLLECTION_NAME, client  # noqa: E402
from qdrant_client.models import PointVectors, SparseVector  # noqa: E402

LOT = 200


def texte_indexe(charge: dict) -> str:
    """Le texte sous lequel le point est indexé — pas toujours son `contenu`.

    Un point-réponse est indexé sous sa **question** : réencoder son `contenu`
    (le texte de la réponse) le rendrait introuvable par la recherche lexicale,
    silencieusement, puisque rien ne lève.

    Un chunk de document est indexé sous `contexte` + `contenu` quand la
    contextualisation a produit un locateur (cf. `services/contextualisation.py`).
    La recomposition est déléguée à ce module, pour qu'il n'existe qu'une seule
    définition de « quel texte a été encodé » : deux implémentations qui
    dériveraient réécriraient ici les vecteurs creux à partir d'un texte que
    l'ingestion n'a jamais encodé, sans que rien ne le signale.
    """
    if charge.get("reponse_id"):
        return charge.get("question_indexee") or charge.get("contenu") or ""
    return recomposer(charge.get("contenu") or "", charge.get("contexte"))


def _identiques(ancien: SparseVector, creux: dict) -> bool:
    """Le vecteur stocké porte-t-il déjà les poids de la formule courante ?

    Un vecteur creux est un ensemble de couples (indice, poids) : l'ordre n'y a
    aucun sens, et les deux sources ne le donnent pas dans le même. On compare
    donc des dictionnaires, pas des listes.
    """
    stocke = dict(zip(ancien.indices, ancien.values, strict=True))
    calcule = dict(zip(creux["indices"], creux["values"], strict=True))
    if stocke.keys() != calcule.keys():
        return False
    return all(abs(stocke[i] - calcule[i]) < 1e-6 for i in stocke)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--appliquer", action="store_true", help="écrit réellement (sinon : simulation)")
    args = parser.parse_args()

    if not client.collection_exists(COLLECTION_NAME):
        print(f"collection « {COLLECTION_NAME} » absente", file=sys.stderr)
        return 1

    print(f"bm25 : K1={K1} B={B} AVG_LEN={AVG_LEN}")
    print(f"mode : {'ÉCRITURE' if args.appliquer else 'simulation (--appliquer pour écrire)'}\n")

    offset = None
    vus = ecrits = vides = inchanges = 0
    while True:
        lot, offset = client.scroll(COLLECTION_NAME, limit=LOT, offset=offset, with_payload=True, with_vectors=True)
        maj = []
        for point in lot:
            vus += 1
            texte = texte_indexe(point.payload or {})
            creux = encoder(texte, est_requete=False)
            if not creux["indices"]:
                # Aucun token signifiant. On réécrit quand même le vecteur vide :
                # laisser l'ancien en place garderait un point trouvable sur des
                # tokens que la tokenisation courante ne produit plus.
                vides += 1

            # Comparaison **indépendante de l'ordre**, et c'est le point délicat :
            # Qdrant restitue les indices triés par ordre croissant, là où
            # `encoder` les produit dans l'ordre de première apparition dans le
            # texte. Comparer les listes telles quelles ne détecte donc jamais un
            # vecteur déjà à jour : le script réécrit tout à chaque passage — sans
            # dommage, puisqu'il est idempotent, mais il ne sait alors plus rien
            # confirmer, et c'est précisément ce qu'on lui demande en simulation.
            ancien = (point.vector or {}).get("sparse")
            if ancien is not None and _identiques(ancien, creux):
                inchanges += 1
                continue

            maj.append(
                PointVectors(
                    id=point.id,
                    vector={"sparse": SparseVector(indices=creux["indices"], values=creux["values"])},
                )
            )

        if maj and args.appliquer:
            client.update_vectors(collection_name=COLLECTION_NAME, points=maj, wait=True)
        ecrits += len(maj)
        print(f"  {vus} points parcourus, {ecrits} à réécrire…", end="\r")

        if offset is None:
            break

    print(f"\n\n{vus} points parcourus")
    print(f"  {ecrits} vecteurs creux {'réécrits' if args.appliquer else 'à réécrire'}")
    print(f"  {inchanges} déjà à jour")
    print(f"  {vides} sans token signifiant (vecteur creux vide)")
    if not args.appliquer:
        print("\nsimulation — relancer avec --appliquer")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
