"""Quel modèle Albert pour le juge du cache — le plus léger qui tienne ?

    PYTHONPATH=. python scripts/eval_juge_modeles.py

`eval_garde_fou.py` établit qu'un juge LLM est le seul garde-fou qui attrape la
négation (7/8, là où le rerank fait pire qu'une pièce lancée). Reste le coût : le
cache existe pour ÉVITER un appel LLM, donc en rajouter un avant de servir n'a de
sens que si ce juge est nettement moins cher que la génération qu'il économise.

D'où ce script : la même tâche, soumise à plusieurs modèles du catalogue Albert,
avec pour chacun la justesse ET la latence. Le choix se fait sur les deux.

Un juge n'a pas le même cahier des charges qu'un générateur. Il ne rédige pas, il
tranche par oui/non. C'est typiquement la tâche où un petit modèle rattrape un
gros — mais c'est aussi une tâche de compréhension fine (« ne … pas », « pour un
alternant »), et c'est exactement là que les petits modèles cèdent. L'un dans
l'autre, ça ne se devine pas, ça se mesure.

Détail d'implémentation : l'appel HTTP est refait ici plutôt que via
`app.services.llm.chat`, parce qu'on doit faire varier le modèle par requête et
relever `usage` et la latence — trois choses que `chat()` ne permet pas. Le corps
de requête est identique au sien.

Opt-in : consomme des tokens Albert (len(MODELES) × 8 appels).
"""

import argparse
import json
import re
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, ".")

from app.config import settings

RACINE = Path(__file__).resolve().parent.parent
DATASET = RACINE / "tests" / "dataset_precision.json"

# Candidats plausibles pour un juge, du plus léger au plus lourd.
# `gpt-oss-120b` est le modèle en service et sert de référence.
MODELES = [
    ("mistralai/Ministral-3-8B-Instruct-2512", "8.9B, généraliste"),
    ("mistralai/Mistral-Small-3.2-24B-Instruct-2506", "24B, moyen"),
    ("openai/gpt-oss-120b", "117B MoE (5.1B actifs), RAISONNEMENT — en service"),
]

VERDICTS = {"SUFFISANTE", "INSUFFISANTE"}

INVITE = """Tu es un contrôleur qualité d'un support interne.

On s'apprête à servir à un employé une réponse DÉJÀ VALIDÉE, tirée d'un cache,
sans qu'aucun humain ne la relise. Ton rôle est d'autoriser ou de bloquer.

QUESTION POSÉE :
{question}

RÉPONSE QUE L'ON S'APPRÊTE À SERVIR :
{reponse}

Cette réponse traite-t-elle correctement et complètement CETTE question précise ?

Réponds INSUFFISANTE si la question ajoute une condition, une restriction, une
négation ou un cas particulier que la réponse ne couvre pas — ou si la réponse
serait trompeuse pour cette question précise, même en étant vraie en général.

Réponds SUFFISANTE seulement si servir cette réponse telle quelle est sans risque.

Ne rédige aucune correction. Réponds uniquement par un objet JSON :
{{"verdict": "SUFFISANTE"}} ou {{"verdict": "INSUFFISANTE"}}"""


def interroger(modele: str, question: str, reponse: str) -> tuple[str, float, int]:
    """Renvoie (verdict, latence_s, tokens_completion). Repli sûr : INCERTAIN."""
    corps = {
        "model": modele,
        "messages": [{"role": "user", "content": INVITE.format(question=question, reponse=reponse)}],
        "temperature": 0,
        # Large à dessein : un modèle à raisonnement consomme ce budget dans un
        # champ `reasoning` AVANT d'émettre le moindre `content`. À 64 tokens,
        # gpt-oss-120b rendait 8 verdicts vides sur 8 — on aurait mesuré le budget,
        # pas le modèle.
        "max_tokens": 2000,
    }
    for tentative in range(5):
        depart = time.monotonic()
        try:
            r = httpx.post(
                f"{settings.albert_llm_url}/chat/completions",
                headers={"Authorization": f"Bearer {settings.albert_api_key}"},
                json=corps,
                timeout=180,
            )
            r.raise_for_status()
        except Exception as erreur:  # noqa: BLE001
            if "429" in str(erreur) and tentative < 4:
                time.sleep(10 * (tentative + 1))
                continue
            print(f"      (échec : {str(erreur)[:100]})")
            return "INCERTAIN", 0.0, 0
        latence = time.monotonic() - depart
        data = r.json()
        contenu = data["choices"][0]["message"].get("content") or ""
        jetons = data.get("usage", {}).get("completion_tokens", 0)
        trouve = re.search(r'"verdict"\s*:\s*"(\w+)"', contenu)
        if trouve and trouve.group(1).upper() in VERDICTS:
            return trouve.group(1).upper(), latence, jetons
        return "INCERTAIN", latence, jetons
    return "INCERTAIN", 0.0, 0


def main() -> int:
    parseur = argparse.ArgumentParser()
    parseur.add_argument("--pause", type=float, default=6.0, help="respiration entre appels (429)")
    args = parseur.parse_args()

    cas = json.loads(DATASET.read_text(encoding="utf-8"))["cas"]
    rag = [c for c in cas if c["attendu"] == "RAG"]

    print(f"\n{'═' * 96}")
    print("QUEL MODÈLE POUR LE JUGE DU CACHE ?")
    print(f"{'═' * 96}")
    print("\n  Tâche : « peut-on servir cette réponse en cache à cette question ? »")
    print("  Un bon juge dit SUFFISANTE sur les cas CACHE, INSUFFISANTE sur les cas RAG.")
    print("  L'erreur qui compte est de dire SUFFISANTE à tort : elle expose une réponse")
    print("  fausse estampillée VALIDÉE. Bloquer à tort ne fait que rendre la main au RAG.\n")

    resultats = {}
    for modele, note in MODELES:
        print(f"\n{'─' * 96}\n{modele}\n   {note}\n{'─' * 96}")
        verdicts, latences, jetons = {}, [], []
        for c in cas:
            v, lat, tok = interroger(modele, c["question_variante"], c["reponse_canonique"])
            verdicts[c["id"]] = v
            if lat:
                latences.append(lat)
                jetons.append(tok)
            attendu = "SUFFISANTE" if c["attendu"] == "CACHE" else "INSUFFISANTE"
            marque = "✓" if v == attendu else "✗"
            danger = "  ⚠ SERT À TORT" if c["attendu"] == "RAG" and v == "SUFFISANTE" else ""
            print(
                f"  {v:<13} {marque}  {lat:>5.1f}s {tok:>5}tok  {c['attendu']:<6} "
                f"{c['gravite'] or '—':<9} {c['id']}{danger}"
            )
            time.sleep(args.pause)

        justes = sum(
            1 for c in cas if verdicts[c["id"]] == ("SUFFISANTE" if c["attendu"] == "CACHE" else "INSUFFISANTE")
        )
        dangereux = [c for c in rag if verdicts[c["id"]] == "SUFFISANTE"]
        critiques = [c for c in dangereux if c["gravite"] == "CRITIQUE"]
        # Un modèle qui répond toujours pareil n'a pas jugé : il a une opinion
        # constante, et son score ne mesure que la composition du jeu de cas.
        # Sans ce test, `INSUFFISANTE` × 8 sort à 5/8 avec 0 erreur dangereuse —
        # en tête du tableau, alors que ce modèle bloquerait 100 % du cache.
        distincts = set(verdicts.values())
        resultats[modele] = {
            "justes": justes,
            "dangereux": len(dangereux),
            "critiques": len(critiques),
            "latence": sum(latences) / len(latences) if latences else 0.0,
            "jetons": sum(jetons) / len(jetons) if jetons else 0,
            "ids_dangereux": [c["id"] for c in dangereux],
            "degenere": next(iter(distincts)) if len(distincts) == 1 else None,
        }

    print(f"\n{'═' * 96}\nSYNTHÈSE\n{'═' * 96}")
    n_cache = len(cas) - len(rag)
    print(f"\n{'modèle':<48} {'justes':>7} {'sert à tort':>12} {'CRITIQUE':>9} {'latence':>9} {'tokens':>8}")
    print(f"{'-' * 96}")
    for modele, _ in MODELES:
        r = resultats[modele]
        drapeau = "  ⚠ VERDICT CONSTANT" if r["degenere"] else ""
        print(
            f"{modele:<48} {r['justes']:>4}/{len(cas):<2} {r['dangereux']:>12} "
            f"{r['critiques']:>9} {r['latence']:>8.1f}s {r['jetons']:>8.0f}{drapeau}"
        )

    print(
        "\n  Comment lire : la colonne « sert à tort » prime sur « justes ». Les deux\n"
        "  erreurs ne se compensent pas et ne doivent pas être moyennées : bloquer à tort\n"
        "  rend la main au RAG, servir à tort expose une réponse fausse estampillée VALIDÉE.\n"
        f"\n  Les deux dégénérescences donnent d'ailleurs un score flatteur sur ce jeu :\n"
        f"  tout bloquer vaut {len(rag)}/{len(cas)} sans jamais être dangereux, tout servir vaut\n"
        f"  {n_cache}/{len(cas)} en exposant {len(rag)} réponses fausses. D'où le drapeau VERDICT CONSTANT :\n"
        "  un modèle qui n'émet qu'un seul verdict n'a pas jugé, il a une opinion fixe,\n"
        "  et son score ne mesure que la composition du jeu de cas.\n"
        "\n  La colonne « tokens » explique la latence : un modèle à raisonnement dépense\n"
        "  des jetons invisibles dans un champ `reasoning` avant d'écrire son verdict."
    )
    for modele, _ in MODELES:
        r = resultats[modele]
        if r["degenere"]:
            print(f"\n  ⚠ {modele} a répondu « {r['degenere']} » aux {len(cas)} cas — score non interprétable.")
        if r["ids_dangereux"]:
            print(f"\n  {modele} sert à tort : {', '.join(r['ids_dangereux'])}")

    print(
        f"\n  ⚠ {len(cas)} cas, dont {len(rag)} du côté RAG. Une différence d'une seule erreur entre\n"
        "  deux modèles n'est pas significative — ce tableau sert à éliminer les modèles\n"
        "  franchement inaptes, pas à départager les deux premiers.\n"
        "\n  ⚠ `temperature=0` ne garantit pas la reproductibilité chez Albert. Cinq mesures\n"
        "  de gpt-oss-120b sur ce jeu ont donné 7/8 quatre fois et 5/8 une fois, à code\n"
        "  identique. Un run isolé ne suffit pas à départager ; répéter avant de conclure."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
