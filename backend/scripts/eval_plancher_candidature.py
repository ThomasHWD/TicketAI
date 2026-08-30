"""Jusqu'où peut-on descendre le plancher de candidature du cache ?

    make up
    PYTHONPATH=. python scripts/eval_plancher_candidature.py

CE QUI EST EN JEU
-----------------
`eval_accord_rag_cache.py` établit que le juge ancré sur les sources ([6]) trie
correctement les 8 cas (8/8, 0 erreur dangereuse, 3 runs). Mais ce résultat est
inatteignable en production tel quel : `question_pipeline.py` fixait alors un unique
plancher de candidature

    SEUIL_SUGGESTION = SEUIL_COSINUS - 0.05      # = 0.85

et `trouver_reponse_reutilisable` écartait tout chunk en dessous. Or les trois
reformulations légitimes du jeu sont à 0.78, 0.75 et 0.71 : **elles ne devenaient
même pas candidates**, le juge ne les voyait jamais. Récolter le bénéfice de [6]
imposait donc de descendre le plancher — et c'est le seul paramètre du nouveau
design qui n'avait jamais été mesuré.

C'est cette mesure qui a fixé `SEUIL_CANDIDAT_CANONIQUE = 0.70`, découplé de
`SEUIL_SUGGESTION` resté à 0.85. Relancer ce script est la seule façon honnête de
justifier un futur déplacement de ce plancher : sa borne basse est un `max` sur les
points indexés, donc elle monte avec le corpus.

LES DEUX RISQUES QU'ON OUVRE EN DESCENDANT
------------------------------------------
1. **MÉSATTRIBUTION.** La variante de la question B peut matcher le point canonique
   de la question A. L'utilisateur reçoit alors une réponse VALIDÉE à une question
   que personne n'a posée. Invisible dans une évaluation par paires (§6.3 du plan) :
   il faut un POOL.

2. **LE DÉPARTAGE PAR `nb_validations`.** `trouver_reponse_reutilisable` choisit par
   `(canonique, nb_validations, score, id)` — **`nb_validations` prime sur le
   score**. Dès qu'il y a plus d'un candidat qualifié, ce n'est donc PAS le mieux
   noté qui est retenu, mais le plus validé. Descendre le plancher augmente
   mécaniquement le nombre de candidats, donc l'emprise de ce départage.

D'où le protocole : on ne demande pas « le bon candidat est-il le mieux noté ? »
(la production ne s'en sert pas pour trancher) mais **« [6] bloque-t-il TOUS les
candidats faux qui se qualifient ? »**. Si oui, le plancher est sûr quel que soit le
candidat que le départage finit par retenir — c'est la seule formulation qui ne
dépende pas d'un `nb_validations` qu'on aurait inventé.

Opt-in : nécessite Qdrant (`make up`) et consomme des tokens Albert.
Aucune écriture en base.
"""

import argparse
import json
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, ".")

from app.config import settings
from app.services.embedding import embed_texts
from app.services.reranker import rerank
from app.services.search import search_hybrid
from scripts.eval_accord_rag_cache import (
    DATASET,
    INVITE_SOURCES,
    VERDICTS_SOURCES,
    cosinus,
    indexer,
    juger,
    nettoyer,
)

RACINE = Path(__file__).resolve().parent.parent

PLANCHERS = [0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90]


def argmax(ligne: list[float]) -> int:
    """Indice du meilleur score de la ligne. Extrait en fonction pour ne pas
    capturer `i` dans une lambda au milieu d'une compréhension (ruff B023)."""
    return max(range(len(ligne)), key=ligne.__getitem__)


def main() -> int:
    parseur = argparse.ArgumentParser()
    parseur.add_argument("--pause", type=float, default=8.0)
    parseur.add_argument("--plancher-teste", type=float, default=0.70, help="plancher soumis au test décisif")
    args = parseur.parse_args()

    cas = json.loads(DATASET.read_text(encoding="utf-8"))["cas"]
    marque = f"PLANCHER-{uuid.uuid4().hex[:8]}"

    print(f"\n{'═' * 104}")
    print("PLANCHER DE CANDIDATURE — jusqu'où descendre sans ouvrir la mésattribution ?")
    print(f"{'═' * 104}")
    print(
        f"\n  planchers en production : {settings.seuil_candidat_canonique:.2f} (canonique) · "
        f"{settings.seuil_suggestion:.2f} (validée non canonique)"
    )
    print(f"  plancher soumis au test décisif : {args.plancher_teste:.2f}")
    print(f"  pool : {len(cas)} réponses canoniques\n")

    # ── Le pool ──────────────────────────────────────────────────────────────
    # Le texte indexé d'une réponse validée est sa question (feedback.py:52-57),
    # pas son contenu : on compare donc variante ↔ question_canonique, comme la
    # production. `texte_indexe` permet de déroger au cas par cas.
    pool = [c.get("texte_indexe") or c["question_canonique"] for c in cas]
    variantes = [c["question_variante"] for c in cas]
    vec = [e["dense"] for e in embed_texts(pool + variantes)]
    vec_pool, vec_var = vec[: len(cas)], vec[len(cas) :]

    # matrice[i][j] = cos(variante i, canonique j)
    matrice = [[cosinus(vec_var[i], vec_pool[j]) for j in range(len(cas))] for i in range(len(cas))]

    # Deux cas partageant la même `question_canonique` (la précision et la
    # reformulation d'une même question validée) pointent vers UN SEUL point
    # indexé. Les compter comme « autre candidat » fabriquerait une
    # mésattribution qui n'existe pas : c'est le même appariement vu deux fois.
    def est_autre(i: int, j: int) -> bool:
        return cas[j]["question_canonique"] != cas[i]["question_canonique"]

    print(f"{'─' * 104}\n[1] MATRICE variante × pool — la diagonale est le bon appariement\n{'─' * 104}\n")
    print(f"{'variante':<34} {'sien':>7} {'meilleur AUTRE':>15}  {'marge':>8}  le plus proche autre")
    print("-" * 104)
    for i, c in enumerate(cas):
        sien = matrice[i][i]
        autres = [(matrice[i][j], cas[j]["id"]) for j in range(len(cas)) if est_autre(i, j)]
        meilleur_autre, id_autre = max(autres)
        mes = "  ⚠ MÉSATTRIBUTION" if meilleur_autre >= sien else ""
        print(f"  {c['id']:<32} {sien:>7.4f} {meilleur_autre:>15.4f}  {sien - meilleur_autre:>+8.4f}  {id_autre}{mes}")

    print(
        "\n  « meilleur AUTRE » exclut les cas qui partagent la même `question_canonique` :\n"
        "  ils désignent le même point indexé, pas un candidat concurrent."
    )

    # ── [1b] la fenêtre de décision ──────────────────────────────────────────
    # Deux quantités, et elles seules, bornent le plancher :
    #   plafond = le plus bas appariement LÉGITIME (sinon on n'admet plus le cache)
    #   plancher = le plus haut appariement FAUX   (sinon on admet une mésattribution)
    legitimes = [(matrice[i][i], cas[i]["id"]) for i in range(len(cas)) if cas[i]["attendu"] == "CACHE"]
    faux_paires = [
        (matrice[i][j], cas[i]["id"], cas[j]["id"]) for i in range(len(cas)) for j in range(len(cas)) if est_autre(i, j)
    ]
    plus_bas_legitime, id_bas = min(legitimes)
    plus_haut_faux, id_v, id_r = max(faux_paires)

    print(f"\n{'─' * 104}\n[1b] FENÊTRE DE DÉCISION\n{'─' * 104}\n")
    print(f"  plus BAS appariement légitime (attendu CACHE) : {plus_bas_legitime:.4f}   {id_bas}")
    print(f"  plus HAUT appariement FAUX  (autre canonique) : {plus_haut_faux:.4f}   {id_v} → {id_r}")
    print(f"  marge                                         : {plus_bas_legitime - plus_haut_faux:+.4f}\n")
    if plus_bas_legitime > plus_haut_faux:
        print(
            f"  → Sur ce jeu, tout plancher dans ]{plus_haut_faux:.4f} ; {plus_bas_legitime:.4f}] admet les\n"
            "    trois reformulations légitimes SANS admettre le moindre appariement faux.\n"
            "    Le juge [6] n'a alors aucune mésattribution à rattraper — il n'est pas\n"
            "    testé sur ce risque, il est seulement contourné par la géométrie du jeu."
        )
    else:
        print("  → Les deux populations se recouvrent : aucun plancher ne les sépare seul.")

    # ── [2] balayage ─────────────────────────────────────────────────────────
    print(f"\n{'─' * 104}\n[2] BALAYAGE DU PLANCHER\n{'─' * 104}\n")
    print(f"{'plancher':>9} {'candidats moy.':>15} {'max':>5} {'variantes ambiguës':>20} {'appariements faux':>19}")
    print("-" * 104)
    for f in PLANCHERS:
        nb = [sum(1 for j in range(len(cas)) if matrice[i][j] >= f) for i in range(len(cas))]
        ambigues = sum(1 for n in nb if n > 1)
        # Compté sur les appariements réellement faux (autre `question_canonique`),
        # pas sur l'argmax de la ligne : l'argmax brut désigne souvent un jumeau
        # partageant le même point indexé, ce qui n'est pas une mésattribution.
        faux = sum(1 for i in range(len(cas)) for j in range(len(cas)) if est_autre(i, j) and matrice[i][j] >= f)
        print(f"{f:>9.2f} {sum(nb) / len(nb):>15.2f} {max(nb):>5} {ambigues:>20} {faux:>19}")

    print(
        "\n  « variantes ambiguës » = plus d'un candidat qualifié. Sur celles-là, la\n"
        "  production NE retient PAS le mieux noté : `trouver_reponse_reutilisable`\n"
        "  départage par `nb_validations` d'abord (question_pipeline.py:172-177).\n"
        "  C'est pourquoi le test qui suit interroge TOUS les candidats faux, pas l'argmax."
    )

    # ── [3] test décisif ─────────────────────────────────────────────────────
    def qualifies(f: float) -> list[tuple[int, int]]:
        return [(i, j) for i in range(len(cas)) for j in range(len(cas)) if est_autre(i, j) and matrice[i][j] >= f]

    f = args.plancher_teste
    a_juger = qualifies(f)
    rabattu = False
    if not a_juger:
        # Aucun appariement faux ne se qualifie au plancher demandé — la
        # géométrie du jeu, pas le juge, écarte la mésattribution. Conclure ici
        # publierait « plancher sûr » sans avoir jamais interrogé [6]. On descend
        # donc SOUS le plus haut appariement faux pour le forcer à se prononcer :
        # c'est un test de robustesse du juge, pas une recommandation de plancher.
        f = round(plus_haut_faux - 0.005, 4)
        a_juger = qualifies(f)
        rabattu = True

    print(f"\n{'─' * 104}\n[3] TEST DÉCISIF au plancher {f:.4f} — [6] bloque-t-il les candidats FAUX ?\n{'─' * 104}")
    if rabattu:
        print(
            f"\n  ⚠ Au plancher demandé ({args.plancher_teste:.2f}), AUCUN appariement faux ne se\n"
            "  qualifie : le jeu ne contient pas de mésattribution à ce niveau. Le plancher\n"
            "  y est donc sûr par construction du jeu, ce qui ne prouve rien sur le juge.\n"
            f"  On descend à {f:.4f} — sous le plus haut appariement faux — pour l'obliger à\n"
            "  se prononcer. Ce chiffre est un stress-test, PAS un plancher recommandé."
        )
    print(f"\n  couples (variante, réponse d'un AUTRE canonique) à juger : {len(a_juger)}\n")

    if not a_juger:
        print("  Aucun couple à juger même après rabattement — jeu trop petit pour ce test.")
        return 0

    domaines = indexer(cas, marque)
    laisses_passer = []
    try:
        extraits_par_variante: dict[int, str] = {}
        for i, _ in a_juger:
            if i in extraits_par_variante:
                continue
            chunks = search_hybrid(cas[i]["question_variante"], domaines[cas[i]["domaine"]], top_k=15)
            chunks = rerank(cas[i]["question_variante"], chunks, top_k=5) or chunks[:5]
            extraits_par_variante[i] = "\n\n".join(f"[extrait {k + 1}] {ch['contenu']}" for k, ch in enumerate(chunks))

        print(f"  {'variante':<34} {'réponse candidate de':<34} {'cos':>7}  verdict [6]")
        print("  " + "-" * 100)
        for i, j in a_juger:
            verdict = juger(
                INVITE_SOURCES,
                VERDICTS_SOURCES,
                question=cas[i]["question_variante"],
                sources=extraits_par_variante[i],
                cachee=cas[j]["reponse_canonique"],
            )
            passe = verdict == "ETAYEE"
            if passe:
                laisses_passer.append((cas[i]["id"], cas[j]["id"], matrice[i][j]))
            print(
                f"  {cas[i]['id']:<34} {cas[j]['id']:<34} {matrice[i][j]:>7.4f}  "
                f"{verdict}{'  ⚠ LAISSE PASSER' if passe else ' ✓'}"
            )
            time.sleep(args.pause)
    finally:
        nettoyer(domaines)

    print(f"\n{'═' * 104}\nVERDICT\n{'═' * 104}\n")
    if laisses_passer:
        print(f"  ⚠ {len(laisses_passer)} candidat(s) FAUX approuvé(s) par [6] à {f:.4f} :")
        for v, r, s in laisses_passer:
            print(f"      « {v} » servie avec la réponse de « {r} »  (cos {s:.4f})")
        print(
            "\n  → [6] seul ne rattrape PAS la mésattribution : il valide qu'une réponse est\n"
            "    étayée par les extraits, pas qu'elle répond à CETTE question. Il faut donc\n"
            "    lui adjoindre [2] (qui, lui, ne voit que la question) — c'est la conception\n"
            "    [7], et c'est un argument mesuré pour [7] plutôt que [6] seul."
        )
    else:
        print(f"  ✓ [6] a bloqué les {len(a_juger)} appariements faux soumis, à {f:.4f}.")

    print(f"\n  Plancher recommandé sur ce jeu : ]{plus_haut_faux:.4f} ; {plus_bas_legitime:.4f}]")
    print(
        f"    borne haute imposée par {id_bas} ({plus_bas_legitime:.4f}) — au-dessus, les\n"
        "    reformulations légitimes ne deviennent jamais candidates et [6] ne sert à rien ;\n"
        f"    borne basse imposée par {id_v} → {id_r} ({plus_haut_faux:.4f}) — en dessous,\n"
        "    des appariements faux entrent et il ne reste que le juge pour les arrêter."
    )
    print(
        f"\n  ⚠ La fenêtre ne fait déjà que {plus_bas_legitime - plus_haut_faux:.3f} de large, et le pool tient en\n"
        f"  {len(cas)} cas sur 4 sujets sans recouvrement — le cas le PLUS favorable possible.\n"
        "  La mésattribution croît avec la taille du corpus : le score effectif est un max\n"
        "  sur N points, statistique d'extremum. La borne basse ne peut que monter, et elle\n"
        "  croisera la borne haute. Autrement dit ce plancher n'est pas une constante à\n"
        "  régler une fois : il faudra le remesurer, et prévoir qu'à corpus suffisant aucun\n"
        "  plancher ne sépare plus les deux populations — c'est alors le juge, seul, qui\n"
        "  tient. Refaire à ≥30 paires par polarité."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
