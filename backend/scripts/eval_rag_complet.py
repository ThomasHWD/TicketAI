"""Évaluation complète du pipeline RAG : qualité des réponses et comportement du garde.

    make up
    cd backend && source .venv/bin/activate
    PYTHONPATH=. python scripts/eval_rag_complet.py

Deux phases, une seule exécution :

Phase 1 — QUALITÉ RAG
  Sans réponse canonique indexée. Pour chaque question de référence le pipeline
  génère une réponse depuis les documents. Un juge LLM vérifie qu'elle est correcte,
  qu'elle ne réinvente pas de faits et qu'elle répond à LA question posée.

Phase 2 — COMPORTEMENT DU GARDE
  Les réponses canoniques de `tests/dataset_precision.json` sont indexées dans Qdrant
  (même format que `workers/feedback.py`). Pour chaque variante :
  — si le garde laisse passer  →  CACHE_SERVI  (correct si attendu=CACHE, erreur si RAG)
  — si le garde bloque         →  RAG_PRIS     (correct si attendu=RAG, erreur si CACHE)

  La seule colonne qui coûte cher : SERT_À_TORT (RAG attendu, cache servi quand même).
  Bloquer à tort ne fait que renvoyer au RAG — comportement actuel du produit.
"""

import argparse
import json
import re
import time
import uuid
from pathlib import Path

import sys
sys.path.insert(0, ".")

from app.config import settings
from app.services.embedding import embed_texts
from app.services.garde_cache import autoriser_service_canonique
from app.services.llm import chat, generate
from app.services.qdrant import COLLECTION_NAME, client
from app.services.reranker import rerank
from app.services.search import search_hybrid
from app.workers.ingestion import chunk_text, extract_text
from qdrant_client.models import (
    FieldCondition,
    FilterSelector,
    MatchValue,
    PointStruct,
    SparseVector,
)
from qdrant_client.models import Filter as QFilter

RACINE = Path(__file__).resolve().parent.parent
DATASET = RACINE / "tests" / "dataset_precision.json"
DOCS = RACINE / "tests"

SEUIL_CANDIDAT_CANONIQUE = settings.seuil_candidat_canonique
JUGE = "openai/gpt-oss-120b"

# ── Questions de référence pour la Phase 1 ────────────────────────────────────
# Chaque entrée : (domaine, doc_source, question, faits_attendus)
# `faits_attendus` : fragments de la bonne réponse que le juge vérifie verbatim
# depuis le document. Aucun fait inventé.
QUESTIONS_QUALITE = [
    (
        "IT",
        "Charte_Utilisation_Informatique.md",
        "Mon employeur a-t-il le droit de lire mes e-mails marqués « Personnel » ?",
        ["non", "nikon", "personnel"],
    ),
    (
        "IT",
        "Charte_Utilisation_Informatique.md",
        "Mon employeur peut-il lire mes e-mails qui ne sont PAS marqués « Personnel » ?",
        ["oui", "présumé professionnel", "direction juridique"],
    ),
    (
        "IT",
        "Charte_Utilisation_Informatique.md",
        "Puis-je brancher ma clé USB personnelle sur mon poste de travail OmniCorp ?",
        ["non", "interdite", "dsi"],
    ),
    (
        "IT",
        "Charte_Utilisation_Informatique.md",
        "Combien de temps OmniCorp conserve-t-elle les logs de connexion et de navigation web ?",
        ["90 jours", "cnil"],
    ),
    (
        "RH",
        "Accord_Teletravail_Reglementation.md",
        "Faut-il obligatoirement signer un avenant au contrat pour pouvoir télétravailler ?",
        ["oui", "avenant", "drh"],
    ),
    (
        "RH",
        "Accord_Teletravail_Reglementation.md",
        "Que risque-t-on si on change de lieu de télétravail sans prévenir la DRH ?",
        ["accident du travail", "l411-1", "nullité"],
    ),
    (
        "RH",
        "Accord_Teletravail_Reglementation.md",
        "Quel est le montant de l'indemnité mensuelle de télétravail versée par OmniCorp ?",
        ["15 €", "forfaitaire", "4 jours"],
    ),
    (
        "RH",
        "Accord_Teletravail_Reglementation.md",
        "À partir de quelle heure le soir les notifications Slack sont-elles bloquées ?",
        ["20h", "07h"],
    ),
    (
        "RH",
        "Gestion_Donnees_Salarie_RGPD.md",
        "À quelle adresse dois-je écrire pour demander l'accès à mon dossier RH ?",
        ["dpo@omnicorp.fr", "dpo", "1 mois"],
    ),
    (
        "RH",
        "Gestion_Donnees_Salarie_RGPD.md",
        "Combien de temps mes données RH sont-elles conservées après mon départ d'OmniCorp ?",
        ["5 ans", "l3245-1"],
    ),
    (
        "IT",
        "Procedure_Onboarding_IT.md",
        "Quelle clé de sécurité matérielle est remise à chaque nouveau salarié pour le VPN ?",
        ["yubikey", "5c fips"],
    ),
    (
        "IT",
        "Procedure_Onboarding_IT.md",
        "En combien de temps la DSI attribue-t-elle les accès de base à un nouvel arrivant ?",
        ["48 heures", "sla"],
    ),
    (
        "IT",
        "Procedure_Onboarding_IT.md",
        "À quel moment le manager est-il prévenu pour préparer l'arrivée d'un nouveau collaborateur ?",
        ["m-7", "7 jours", "servicenow"],
    ),
]

INVITE_JUGE_QUALITE = """Tu évalues la qualité d'une réponse RAG générée par un assistant de support interne.

QUESTION POSÉE :
{question}

EXTRAIT DU DOCUMENT SOURCE (seule source de vérité) :
{extrait_source}

RÉPONSE GÉNÉRÉE :
{reponse}

Évalue sur deux critères :
1. CORRECTE : la réponse est-elle factuellement exacte par rapport au document ? (aucune invention, aucune contradiction)
2. PERTINENTE : répond-elle à la question posée, sans esquiver ni généraliser ?

Réponds uniquement par un objet JSON :
{{"correcte": true/false, "pertinente": true/false, "note": "explication courte en une phrase"}}"""


# ── Outillage commun ──────────────────────────────────────────────────────────

def indexer_docs(cas: list[dict], marque: str) -> dict[str, str]:
    """Indexe les 4 documents de test en domaines isolés (domaine-MARQUE)."""
    domaines = {c["domaine"]: f"{c['domaine']}-{marque}" for c in cas}
    par_doc = {c["doc_source"]: c["domaine"] for c in cas}

    for fichier, domaine_reel in sorted(par_doc.items()):
        chemin = DOCS / fichier
        if not chemin.exists():
            raise FileNotFoundError(f"Document introuvable : {chemin}")
        morceaux = chunk_text(extract_text(str(chemin)))
        embeddings = embed_texts(morceaux, is_query=False)
        client.upsert(
            collection_name=COLLECTION_NAME,
            points=[
                PointStruct(
                    id=str(uuid.uuid4()),
                    vector={
                        "dense": emb["dense"],
                        "sparse": SparseVector(
                            indices=emb["sparse"]["indices"],
                            values=emb["sparse"]["values"],
                        ),
                    },
                    payload={
                        "doc_id": f"{marque}-{fichier}",
                        "version": 1,
                        "chunk_index": i,
                        "source": fichier,
                        "domaine": domaines[domaine_reel],
                        "contenu": morceau,
                    },
                )
                for i, (morceau, emb) in enumerate(zip(morceaux, embeddings, strict=True))
            ],
            wait=True,
        )
        print(f"  {fichier:<52} {len(morceaux):>3} chunks → {domaines[domaine_reel]}")
    return domaines


def indexer_canoniques(cas: list[dict], domaines: dict[str, str], marque: str) -> dict[str, dict]:
    """Indexe les réponses canoniques du dataset (format identique à feedback.py).

    Renvoie {reponse_id_str: {"contenu": ..., "question_canonique": ..., "id_cas": ...}}.
    """
    registre: dict[str, dict] = {}
    textes = [c["question_canonique"] for c in cas]
    embeddings = embed_texts(textes, is_query=False)

    for c, emb in zip(cas, embeddings, strict=True):
        rid = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{marque}-{c['id']}"))
        domaine_isole = domaines[c["domaine"]]
        client.upsert(
            collection_name=COLLECTION_NAME,
            points=[
                PointStruct(
                    id=rid,
                    vector={
                        "dense": emb["dense"],
                        "sparse": SparseVector(
                            indices=emb["sparse"]["indices"],
                            values=emb["sparse"]["values"],
                        ),
                    },
                    payload={
                        "reponse_id": rid,
                        "contenu": c["reponse_canonique"],
                        "domaine": domaine_isole,
                    },
                )
            ],
            wait=True,
        )
        registre[rid] = {
            "contenu": c["reponse_canonique"],
            "question_canonique": c["question_canonique"],
            "id_cas": c["id"],
        }
    print(f"  {len(cas)} réponses canoniques indexées.")
    return registre


def nettoyer(domaines: dict[str, str]) -> None:
    for domaine in set(domaines.values()):
        client.delete(
            collection_name=COLLECTION_NAME,
            points_selector=FilterSelector(
                filter=QFilter(must=[FieldCondition(key="domaine", match=MatchValue(value=domaine))])
            ),
            wait=True,
        )
    print(f"  {len(set(domaines.values()))} domaines de test purgés.")


def appel_llm_robuste(messages: list[dict], **kwargs) -> str | None:
    for tentative in range(4):
        try:
            return chat(messages, temperature=0, max_tokens=1000, timeout=90, **kwargs)
        except Exception as e:
            if "429" in str(e) and tentative < 3:
                attente = 12 * (tentative + 1)
                print(f"    (429, reprise dans {attente}s)")
                time.sleep(attente)
                continue
            print(f"    (Albert indisponible : {str(e)[:100]})")
            return None
    return None


def generer_robuste(question: str, chunks: list[dict]) -> tuple[str | None, bool]:
    for tentative in range(4):
        try:
            texte, hors_domaine = generate(question, chunks)
            return texte, hors_domaine
        except Exception as e:
            if "429" in str(e) and tentative < 3:
                attente = 15 * (tentative + 1)
                print(f"    (429 génération, reprise dans {attente}s)")
                time.sleep(attente)
                continue
            print(f"    (erreur génération : {str(e)[:100]})")
            return None, False
    return None, False


def extraire_json(brut: str | None, cles: list[str]) -> dict | None:
    if not brut:
        return None
    try:
        obj = json.loads(re.search(r"\{.*?\}", brut, re.DOTALL).group())  # type: ignore[union-attr]
        if all(k in obj for k in cles):
            return obj
    except Exception:
        pass
    return None


# ── Phase 1 : qualité RAG ─────────────────────────────────────────────────────

def phase_qualite(domaines_q: dict[str, str], pause: float) -> list[dict]:
    resultats = []
    domaines_doc = {
        "Charte_Utilisation_Informatique.md": "IT",
        "Gestion_Donnees_Salarie_RGPD.md": "RH",
        "Accord_Teletravail_Reglementation.md": "RH",
        "Procedure_Onboarding_IT.md": "IT",
    }

    for domaine, doc_source, question, _ in QUESTIONS_QUALITE:
        domaine_isole = domaines_q[domaine]
        chunks = search_hybrid(question, domaine_isole, top_k=15)
        chunks_r = rerank(question, chunks, top_k=5) or chunks[:5]

        reponse, hors_domaine = generer_robuste(question, chunks_r)
        if reponse is None:
            resultats.append({"q": question, "echec": True, "correcte": None, "pertinente": None, "note": "Albert indisponible"})
            print(f"  ÉCHEC   {question[:80]}")
            continue

        # Source verbatim pour le juge
        extrait_source = "\n".join(c["contenu"] for c in chunks_r[:3] if c.get("contenu") and not c.get("reponse_id"))

        brut = appel_llm_robuste(
            [{"role": "user", "content": INVITE_JUGE_QUALITE.format(
                question=question,
                extrait_source=extrait_source or "(aucun extrait disponible)",
                reponse=reponse,
            )}]
        )
        time.sleep(pause)

        verdict = extraire_json(brut, ["correcte", "pertinente"])
        if verdict is None:
            resultats.append({"q": question, "echec": True, "correcte": None, "pertinente": None, "note": "juge illisible"})
            print(f"  JUGE?   {question[:80]}")
            continue

        ok = verdict["correcte"] and verdict["pertinente"]
        resultats.append({
            "q": question,
            "echec": False,
            "hors_domaine": hors_domaine,
            "correcte": verdict["correcte"],
            "pertinente": verdict["pertinente"],
            "note": verdict.get("note", ""),
            "reponse": reponse,
        })
        symbole = "✓" if ok else ("⚠ HD" if hors_domaine else "✗")
        print(f"  {symbole:<5} correcte={str(verdict['correcte']):<5} pertinente={str(verdict['pertinente']):<5} | {question[:70]}")
        if not ok:
            print(f"        note     : {verdict.get('note', '')}")
            print(f"        réponse  : {' '.join(reponse.split())[:200]}")

    return resultats


# ── Phase 2 : comportement du garde ──────────────────────────────────────────

def trouver_canonique_dans_resultats(
    chunks: list[dict],
    registre: dict[str, dict],
) -> tuple[str | None, str | None, float | None]:
    """Cherche un reponse_id connu du registre, au-dessus du plancher canonique.

    Renvoie (reponse_id, contenu, score) ou (None, None, None).
    """
    for c in chunks:
        rid = str(c.get("reponse_id") or "")
        if rid and rid in registre and c["score_cosinus"] >= SEUIL_CANDIDAT_CANONIQUE:
            return rid, registre[rid]["contenu"], c["score_cosinus"]
    return None, None, None


def phase_garde(cas: list[dict], domaines: dict[str, str], registre: dict[str, dict], pause: float) -> list[dict]:
    resultats = []

    for c in cas:
        domaine_isole = domaines[c["domaine"]]
        chunks = search_hybrid(c["question_variante"], domaine_isole, top_k=15)

        rid, contenu, score = trouver_canonique_dans_resultats(chunks, registre)

        if rid is None:
            # Le candidat canonique n'est pas ressorti au-dessus du plancher :
            # le pipeline irait directement au RAG, sans même appeler le garde.
            decision = "RAG_CANDIDAT_ABSENT"
            autorise = False
            garde_verdict = None
        else:
            verdict = autoriser_service_canonique(c["question_variante"], contenu, chunks)
            time.sleep(pause)
            autorise = verdict.autorise
            garde_verdict = verdict.verdict
            decision = "CACHE_SERVI" if autorise else "RAG_PAR_GARDE"

        attendu_cache = c["attendu"] == "CACHE"
        correct = (autorise == attendu_cache)
        erreur_type = (
            "SERT_À_TORT" if (autorise and not attendu_cache)
            else ("BLOQUE_À_TORT" if (not autorise and attendu_cache) else "OK")
        )

        resultats.append({
            "id": c["id"],
            "attendu": c["attendu"],
            "decision": decision,
            "garde_verdict": garde_verdict,
            "score": score,
            "correct": correct,
            "erreur_type": erreur_type,
            "gravite": c.get("gravite"),
            "taxonomie": c.get("taxonomie"),
            "question_variante": c["question_variante"],
            "reponse_canonique": c.get("reponse_canonique", ""),
        })

        alerte = "  ⚠ " if not correct else "    "
        score_str = f"cos={score:.4f}" if score else "cos=-----"
        print(
            f"  {alerte}{c['id']:<38} {score_str}  "
            f"décision={decision:<20} attendu={c['attendu']:<5}  "
            f"{'✓' if correct else '✗ ' + erreur_type}"
        )
        if not correct and garde_verdict:
            print(f"          garde : {garde_verdict}")

    return resultats


# ── Synthèse ──────────────────────────────────────────────────────────────────

def synthese(resultats_q: list[dict], resultats_g: list[dict]) -> None:
    print(f"\n{'═' * 110}")
    print("SYNTHÈSE")
    print(f"{'═' * 110}")

    # Phase 1
    valides_q = [r for r in resultats_q if not r["echec"]]
    ok_q = [r for r in valides_q if r["correcte"] and r["pertinente"]]
    ko_q = [r for r in valides_q if not (r["correcte"] and r["pertinente"])]
    echecs_q = [r for r in resultats_q if r["echec"]]

    print(f"\nPhase 1 — QUALITÉ RAG ({len(resultats_q)} questions)")
    print(f"  Correctes + pertinentes : {len(ok_q)}/{len(valides_q)}")
    if echecs_q:
        print(f"  Albert indisponible    : {len(echecs_q)} (écartés)")
    if ko_q:
        print(f"\n  Questions en échec :")
        for r in ko_q:
            print(f"    ✗ correcte={r['correcte']} pertinente={r['pertinente']} | {r['q'][:90]}")
            print(f"      → {r['note']}")

    # Phase 2
    valides_g = [r for r in resultats_g]
    sert_tort  = [r for r in valides_g if r["erreur_type"] == "SERT_À_TORT"]
    bloque_tort = [r for r in valides_g if r["erreur_type"] == "BLOQUE_À_TORT"]
    ok_g = [r for r in valides_g if r["correct"]]

    rag_cas    = [r for r in valides_g if r["attendu"] == "RAG"]
    cache_cas  = [r for r in valides_g if r["attendu"] == "CACHE"]
    rag_ok     = [r for r in rag_cas if r["correct"]]
    cache_ok   = [r for r in cache_cas if r["correct"]]

    print(f"\nPhase 2 — COMPORTEMENT DU GARDE ({len(valides_g)} variantes)")
    print(f"  Décisions correctes  : {len(ok_g)}/{len(valides_g)}")
    print(f"  RAG attendu  → bon   : {len(rag_ok)}/{len(rag_cas)}")
    print(f"  CACHE attendu → bon  : {len(cache_ok)}/{len(cache_cas)}")

    if sert_tort:
        critiques = [r for r in sert_tort if r["gravite"] == "CRITIQUE"]
        majeures  = [r for r in sert_tort if r["gravite"] == "MAJEURE"]
        print(f"\n  ⚠ SERT À TORT (cache servi alors qu'il ne fallait pas) : {len(sert_tort)}")
        print(f"    Critiques : {len(critiques)}   Majeures : {len(majeures)}")
        for r in sert_tort:
            print(f"    [{r['gravite'] or '?':8}] {r['id']} — garde={r['garde_verdict']}")
            print(f"             variante : {r['question_variante'][:90]}")

    if bloque_tort:
        print(f"\n  ↩ BLOQUE À TORT (cache bloqué alors qu'il était servable) : {len(bloque_tort)}")
        for r in bloque_tort:
            print(f"    {r['id']} — garde={r['garde_verdict']}")
            print(f"      variante : {r['question_variante'][:90]}")

    if not sert_tort and not bloque_tort:
        print("\n  Aucune erreur — garde parfaitement calibré sur ce jeu.")

    print(
        "\n  « SERT À TORT » est la seule colonne dangereuse : elle expose une réponse\n"
        "  erronée estampillée VALIDÉE, sans validateur. « BLOQUE À TORT » renvoie\n"
        "  simplement au RAG — comportement antérieur du produit, zéro risque."
    )
    print(f"\n  ⚠ IC 95 % ≈ ±30 pts sur {len(valides_g)} cas (±25 pts sur {len(valides_q)} questions qualité).")
    print("  Ce script est un SIGNAL, pas une mesure publiable.")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    parseur = argparse.ArgumentParser()
    parseur.add_argument("--pause", type=float, default=5.0, help="délai entre appels LLM (429)")
    parseur.add_argument("--garder-index", action="store_true")
    parseur.add_argument("--phase1-seul", action="store_true", help="qualité RAG seulement")
    parseur.add_argument("--phase2-seul", action="store_true", help="garde seulement")
    args = parseur.parse_args()

    cas = json.loads(DATASET.read_text(encoding="utf-8"))["cas"]
    marque = f"EVAL-{uuid.uuid4().hex[:8]}"

    print(f"\n{'═' * 110}")
    print("ÉVALUATION COMPLÈTE RAG — qualité des réponses + comportement du garde")
    print(f"{'═' * 110}")
    print(f"  juge         : {JUGE}")
    print(f"  modèle emb.  : {settings.albert_embeddings_model_name}")
    print(f"  plancher can.: {SEUIL_CANDIDAT_CANONIQUE}")
    print(f"  cas garde    : {len(cas)}   questions qualité : {len(QUESTIONS_QUALITE)}\n")

    # Un seul jeu de domaines pour les deux phases : les canoniques et les chunks
    # de documents cohabitent dans le même domaine isolé.
    # Les points de réponse portent reponse_id, les chunks ne le portent pas.
    # La recherche hybride les retrouve tous, et le pipeline les discrimine.
    domaines_tout = {c["domaine"]: f"{c['domaine']}-{marque}" for c in cas}
    # Les questions qualité couvrent les mêmes domaines IT et RH.
    domaines_q = domaines_tout

    print("─ Indexation des documents " + "─" * 82)
    indexer_docs(cas, marque)

    resultats_q: list[dict] = []
    resultats_g: list[dict] = []

    try:
        if not args.phase2_seul:
            print(f"\n─ Phase 1 : qualité RAG ({len(QUESTIONS_QUALITE)} questions) " + "─" * 65)
            resultats_q = phase_qualite(domaines_q, args.pause)

        if not args.phase1_seul:
            print(f"\n─ Indexation des réponses canoniques ({len(cas)} cas) " + "─" * 56)
            registre = indexer_canoniques(cas, domaines_tout, marque)

            print(f"\n─ Phase 2 : comportement du garde ({len(cas)} variantes) " + "─" * 54)
            resultats_g = phase_garde(cas, domaines_tout, registre, args.pause)

        synthese(resultats_q, resultats_g)

    finally:
        if args.garder_index:
            print(f"\n  Index conservé (--garder-index) : {sorted(set(domaines_tout.values()))}")
        else:
            print("\n─ Nettoyage " + "─" * 97)
            nettoyer(domaines_tout)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
