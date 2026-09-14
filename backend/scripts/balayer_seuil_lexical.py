"""Balaye SEUIL_LEXICAL_PAR_TERME en rejouant une campagne déjà mesurée.

**Zéro appel Albert.** La campagne enregistre pour chaque cas le cosinus, le score
BM25 par terme, la canonicité du candidat et le verdict du juge. La décision étant
déterministe à partir de ces valeurs, on la recalcule à d'autres seuils.

Le balayage ne va que **vers le haut** : durcir la porte lexicale retire des cas au
juge, elle n'en ajoute jamais — donc tous les verdicts nécessaires sont déjà connus.
Descendre exigerait de nouveaux appels.

Usage :
    PYTHONPATH=. python scripts/balayer_seuil_lexical.py /tmp/campagne_apres_correctif.json

⚠️  Une approximation, à connaître : la campagne n'enregistre que le **meilleur**
candidat. Si un seuil plus dur l'élimine, un candidat de second rang aurait pu
prendre sa place ; le rejeu classe alors le cas en RAG. Les colonnes marquées
« éliminés » comptent ces cas, qui bornent l'erreur.
"""

import json
import sys
from collections import Counter

SEUIL_COSINUS = 0.80
SEUIL_SUGGESTION = 0.75
SEUILS = [1.0, 1.2, 1.5, 2.0, 2.5, 3.0, 4.0, 99.0]  # 99 = porte lexicale fermée


def rejouer(cas: dict, seuil_lexical: float) -> tuple[str, bool, bool]:
    """(branche, a_saisi_le_juge, candidat_elimine) pour ce seuil."""
    if cas.get("candidat") is None:
        return "RAG", False, False

    cos = cas.get("score_candidat") or 0.0
    lex = cas.get("score_lexical") or 0.0

    def franchit(seuil_cos: float) -> bool:
        return cos >= seuil_cos or lex >= seuil_lexical

    # Étage de sélection (trouver_reponse_reutilisable).
    if not franchit(SEUIL_SUGGESTION):
        return "RAG", False, True

    servable = cos >= SEUIL_SUGGESTION

    if cas.get("candidat_canonique") and franchit(SEUIL_COSINUS):
        verdict = cas.get("verdict_garde")
        if verdict is None:  # cas jamais soumis au juge : indécidable hors ligne
            return "?", True, False
        if verdict:
            return "CANONIQUE", True, False
        return ("SUGGESTION" if servable else "RAG"), True, False

    return ("SUGGESTION" if servable else "RAG"), False, False


def main() -> None:
    chemin = sys.argv[1] if len(sys.argv) > 1 else "/tmp/campagne_apres_correctif.json"
    cas = json.load(open(chemin))

    print(f"{len(cas)} cas rejoués depuis {chemin}")
    print(f"SEUIL_COSINUS={SEUIL_COSINUS} · SEUIL_SUGGESTION={SEUIL_SUGGESTION}\n")
    entete = (
        f"{'seuil':>6} | {'CANON':>5} {'SUGG':>5} {'RAG':>4} | "
        f"{'conformes':>9} | {'juge':>4} | {'faux+':>5} | {'éliminés':>8}"
    )
    print(entete)
    print("-" * len(entete))

    for seuil in SEUILS:
        branches = Counter()
        conformes = juge = faux_positifs = elimines = indecidables = 0
        for c in cas:
            branche, saisi, elimine = rejouer(c, seuil)
            if branche == "?":
                indecidables += 1
                continue
            branches[branche] += 1
            juge += saisi
            elimines += elimine
            if branche == c["attendu"]:
                conformes += 1
            # Faux positif : servi sans revue une réponse hors cible.
            if branche == "CANONIQUE" and c.get("cible_attendue") and c["candidat"] != c["cible_attendue"]:
                faux_positifs += 1

        libelle = "fermée" if seuil >= 99 else f"{seuil:.1f}"
        alerte = "  ⚠️ INDÉCIDABLES" if indecidables else ""
        print(
            f"{libelle:>6} | {branches['CANONIQUE']:>5} {branches['SUGGESTION']:>5} {branches['RAG']:>4} | "
            f"{conformes:>6}/{len(cas):<2} | {juge:>4} | {faux_positifs:>5} | {elimines:>8}{alerte}"
        )


if __name__ == "__main__":
    main()
