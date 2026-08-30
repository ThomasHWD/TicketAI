"""Le rerank suffit-il à garder le cache, ou faut-il un juge LLM ?

    PYTHONPATH=. python scripts/eval_garde_fou.py

`eval_cache_over_hit.py` établit que le cosinus seul ne peut pas décider (AUC 0
sur le jeu adversarial). Restent deux garde-fous candidats, à placer **avant** de
servir une réponse depuis le cache :

  (c) RERANK — passer (question posée, réponse en cache) au cross-encoder Albert
      et refuser de servir sous un certain score de pertinence ;
  (d) JUGE LLM — un appel `chat` court, température 0, qui répond si la réponse
      en cache traite *bien cette question-là*.

La question à trancher n'est pas « lequel est le meilleur » mais « (c) suffit-il ? ».
Elle a une réponse mesurable : le garde-fou doit donner un score HAUT aux cas
`attendu=CACHE` et BAS aux cas `attendu=RAG`. S'il ne les sépare pas, il ne peut
pas servir de garde-fou, quelle que soit sa finesse par ailleurs.

Hypothèse à falsifier, et raison d'être de ce script : **un reranker est entraîné
pour la PERTINENCE, pas pour la CORRECTION.** Sur `nikon-mail-non-marque`, la
réponse en cache parle bien d'employeur, d'e-mails, de l'arrêt Nikon : elle est
éminemment *pertinente* pour la question — et pourtant elle affirme l'inverse de
la bonne réponse. Si cette intuition est juste, le rerank note ce cas HAUT et
laisse passer le plus grave. Ce script le vérifie au lieu de le supposer.

Opt-in : consomme des tokens Albert (8 rerank + 8 chat).
"""

import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, ".")

from app.services.llm import chat
from app.services.reranker import rerank

RACINE = Path(__file__).resolve().parent.parent
DATASET = RACINE / "tests" / "dataset_precision.json"

# Convention reprise de `services/reverification.py:juger` : une sortie illisible
# vaut INCERTAIN, jamais « sers la réponse ». Le repli par défaut doit toujours
# aller vers la revue humaine — un garde-fou qui échoue en laissant passer n'est
# pas un garde-fou.
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


def juger(question: str, reponse: str) -> str:
    """Un appel température 0, repli sûr vers INCERTAIN.

    `max_tokens` est large, et ce n'est pas du confort. Le modèle servi par Albert
    (`openai/gpt-oss-120b`) est un modèle À RAISONNEMENT : il consomme le budget de
    sortie dans un champ `reasoning` séparé avant d'émettre le moindre `content`.
    Un premier essai à 64 tokens a rendu 8 verdicts vides sur 8 — `content: None`,
    `finish_reason: "length"`, `completion_tokens: 0` — c'est-à-dire un « le juge
    LLM ne sait pas décider » entièrement fabriqué par un budget trop court.
    """
    brut = ""
    for tentative in range(5):
        try:
            brut = chat(
                [{"role": "user", "content": INVITE.format(question=question, reponse=reponse)}],
                temperature=0,
                max_tokens=2000,
                timeout=120,
            )
            break
        except Exception as erreur:  # noqa: BLE001 — une panne Albert doit bloquer, pas planter
            if "429" in str(erreur) and tentative < 4:
                # Albert limite le débit. Sans ce repli, l'indisponibilité se lirait
                # comme un « le juge ne sait pas trancher » — on mesurerait le quota,
                # pas le modèle.
                attente = 10 * (tentative + 1)
                print(f"    (429, nouvelle tentative dans {attente}s)")
                time.sleep(attente)
                continue
            print(f"    (échec Albert : {str(erreur)[:120]})")
            return "INCERTAIN"

    trouve = re.search(r'"verdict"\s*:\s*"(\w+)"', brut or "")
    if trouve and trouve.group(1).upper() in VERDICTS:
        return trouve.group(1).upper()
    return "INCERTAIN"


def auc(positifs: list[float], negatifs: list[float]) -> float:
    if not positifs or not negatifs:
        return 0.5
    gains = sum(1.0 if p > n else 0.5 if p == n else 0.0 for p in positifs for n in negatifs)
    return gains / (len(positifs) * len(negatifs))


def main() -> int:
    cas = json.loads(DATASET.read_text(encoding="utf-8"))["cas"]

    print(f"\n{'═' * 92}")
    print("(c) RERANK vs (d) JUGE LLM — appliqués à la réponse en cache, avant de la servir")
    print(f"{'═' * 92}")
    print("\n  Protocole : pour chaque cas, on soumet la QUESTION VARIANTE et la RÉPONSE")
    print("  CANONIQUE qu'on s'apprête à servir. Un bon garde-fou doit dire « sers »")
    print("  sur les cas CACHE et « ne sers pas » sur les cas RAG.\n")

    print(f"{'rerank':>8}  {'juge LLM':<13} {'attendu':<8} {'gravité':<9} id")
    print(f"{'-' * 92}")

    for c in cas:
        note = rerank(c["question_variante"], [{"contenu": c["reponse_canonique"]}], top_k=1)
        c["rerank"] = note[0]["rerank_score"] if note else None
        c["juge"] = juger(c["question_variante"], c["reponse_canonique"])
        time.sleep(8)  # respiration : Albert limite le débit du /chat/completions

        attendu_juge = "SUFFISANTE" if c["attendu"] == "CACHE" else "INSUFFISANTE"
        marque = "✓" if c["juge"] == attendu_juge else "✗"
        score = f"{c['rerank']:.4f}" if c["rerank"] is not None else "  n/a"
        print(f"{score:>8}  {c['juge']:<11} {marque}  {c['attendu']:<8} {c['gravite'] or '—':<9} {c['id']}")

    cache = [c for c in cas if c["attendu"] == "CACHE"]
    rag = [c for c in cas if c["attendu"] == "RAG"]

    # ── (c) le rerank ────────────────────────────────────────────────────────
    print(f"\n{'─' * 92}\n(c) RERANK\n{'─' * 92}")
    notes_cache = [c["rerank"] for c in cache if c["rerank"] is not None]
    notes_rag = [c["rerank"] for c in rag if c["rerank"] is not None]
    if notes_cache and notes_rag:
        marge = min(notes_cache) - max(notes_rag)
        aire = auc(notes_cache, notes_rag)
        print(f"  cas CACHE (doivent scorer HAUT) : min {min(notes_cache):.4f}  max {max(notes_cache):.4f}")
        print(f"  cas RAG   (doivent scorer BAS)  : min {min(notes_rag):.4f}  max {max(notes_rag):.4f}")
        print(f"  marge : {marge:+.4f}   AUC : {aire:.3f}")
        if marge > 0:
            print("\n  → Séparable : un seuil de rerank suffirait sur ce jeu de cas.")
        else:
            coupables = [c for c in rag if c["rerank"] is not None and c["rerank"] >= min(notes_cache)]
            print(
                "\n  → NON séparable : aucun seuil de rerank ne trie ces cas.\n"
                "    Le reranker note la PERTINENCE (« ce texte parle-t-il du sujet ? »),\n"
                "    pas la CORRECTION (« ce texte répond-il juste à CETTE question ? »).\n"
                "    Cas qui passeraient au travers : " + ", ".join(c["id"] for c in coupables)
            )

    # ── (d) le juge LLM ──────────────────────────────────────────────────────
    print(f"\n{'─' * 92}\n(d) JUGE LLM\n{'─' * 92}")
    justes = sum(1 for c in cas if c["juge"] == ("SUFFISANTE" if c["attendu"] == "CACHE" else "INSUFFISANTE"))
    dangereux = [c for c in rag if c["juge"] == "SUFFISANTE"]
    prudents = [c for c in cache if c["juge"] != "SUFFISANTE"]

    print(f"  verdicts corrects : {justes}/{len(cas)}")
    print(f"  ERREURS DANGEREUSES (sert alors qu'il ne faut pas) : {len(dangereux)}", end="")
    print(f"  → {', '.join(c['id'] for c in dangereux)}" if dangereux else "")
    print(f"  erreurs prudentes  (bloque alors qu'il pourrait servir) : {len(prudents)}", end="")
    print(f"  → {', '.join(c['id'] for c in prudents)}" if prudents else "")

    critique_rate = [c for c in dangereux if c["gravite"] == "CRITIQUE"]
    print(
        "\n  Les deux erreurs n'ont pas le même coût : bloquer à tort ne fait que\n"
        "  renvoyer la question au RAG (elle sera relue par un humain) ; servir à tort\n"
        "  expose une réponse fausse estampillée VALIDÉE. Seule la première colonne\n"
        "  doit être proche de zéro."
    )
    if critique_rate:
        print(f"\n  ⚠ CAS CRITIQUE LAISSÉ PASSER : {', '.join(c['id'] for c in critique_rate)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
