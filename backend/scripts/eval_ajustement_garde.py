"""Recherche d'un meilleur calibrage des juges du garde cache.

    cd backend && source .venv/bin/activate
    PYTHONPATH=. python scripts/eval_ajustement_garde.py

CONTEXTE
--------
Sur 14 variantes, la conjonction actuelle (pertinence AND ancrage) produit :
  - 0 SERT_À_TORT   ✓  (propriété critique, ne doit jamais régresser)
  - 5 BLOQUE_À_TORT ✗  (reformulations légitimes renvoyées au RAG inutilement)

Les 5 blocages se répartissent en trois causes :
  (a) Juge-pertinence trop strict  → logs-parefeu, rgpd-apres-depart-reformule
  (b) Juge-ancrage trop strict     → teletravail-montant-reformule, onboarding-yubikey-reformule
  (c) Candidat non trouvé en retrieval (cos < plancher) → teletravail-avenant-reformule

Ce script teste 6 stratégies de garde sur le même jeu, avec K=2 répétitions
par juge pour estimer la variance (Albert n'est pas reproductible à température 0).
Unanimité requise pour servir dans les stratégies à répétitions.

Stratégies comparées
--------------------
  A   production actuelle : pertinence_orig ET ancrage_orig  (court-circuit sur INSUFFISANTE)
  B   pertinence seule    : pertinence_orig uniquement
  C   ancrage seul        : ancrage_orig uniquement
  D   pertinence_mod ET ancrage_orig
  E   pertinence_orig ET ancrage_mod
  F   pertinence_mod ET ancrage_mod  ← hypothèse la plus optimiste

Résultat attendu : identifier la stratégie qui maximise CACHE_CORRECT sans
introduire de SERT_À_TORT. Toute stratégie avec >= 1 SERT_À_TORT est éliminée.
"""

import argparse
import json
import re
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, ".")

from app.config import settings
from app.services.embedding import embed_texts
from app.services.llm import chat
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
MAX_EXTRAITS = 5

# ── Invites originales (identiques à garde_cache.py — ne pas modifier) ───────

PERTINENCE_ORIG = """Tu es un contrôleur qualité d'un support interne.

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

SOURCES_ORIG = """Tu contrôles le cache de réponses d'un support interne.

Une réponse DÉJÀ VALIDÉE va être servie à un employé sans qu'aucun humain ne la
relise. Tu dois vérifier qu'elle est ENTIÈREMENT ÉTAYÉE par les documents de
référence POUR LA QUESTION EXACTEMENT POSÉE.

QUESTION POSÉE :
{question}

EXTRAITS DES DOCUMENTS DE RÉFÉRENCE (seule source de vérité admise) :
{sources}

RÉPONSE EN CACHE, celle qu'on servirait :
{cachee}

Réponds NON_ETAYEE si l'un de ces points est vrai :
- un élément de la réponse en cache n'apparaît pas dans les extraits ;
- les extraits contredisent la réponse en cache, même partiellement, et en
  particulier sur la polarité (oui / non, autorisé / interdit) ;
- la question porte sur un cas particulier, une condition, une population, une
  période ou une entité dont les extraits ne disent rien. Le silence des documents
  n'autorise JAMAIS à servir : c'est une réponse à donner, pas une lacune à combler.

Réponds ETAYEE seulement si les extraits suffisent à établir que la réponse en cache
répond correctement et complètement à cette question précise.

N'utilise aucune connaissance extérieure aux extraits. Ne rédige aucune correction.
Réponds uniquement par un objet JSON :
{{"verdict": "ETAYEE"}} ou {{"verdict": "NON_ETAYEE"}}"""

# ── Invites modifiées ─────────────────────────────────────────────────────────
# Hypothèse : le juge-pertinence confond « reformulation » et « restriction »
# quand le vocabulaire diffère sans que le sens change. L'invite modifiée
# explicite la différence : seule une restriction sémantique réelle justifie
# INSUFFISANTE, pas un changement de surface.

PERTINENCE_MOD = """Tu es un contrôleur qualité d'un support interne.

On s'apprête à servir à un employé une réponse DÉJÀ VALIDÉE, tirée d'un cache,
sans qu'aucun humain ne la relise. Ton rôle est d'autoriser ou de bloquer.

QUESTION POSÉE :
{question}

RÉPONSE QUE L'ON S'APPRÊTE À SERVIR :
{reponse}

Cette réponse traite-t-elle correctement et complètement CETTE question précise ?

Réponds INSUFFISANTE si la réponse serait inexacte ou trompeuse pour CETTE question.
C'est le cas notamment quand la question :
— inverse la polarité par une négation (« qui ne sont pas », « sans signer »,
  « sans avenant ») ;
— porte sur une catégorie de personnes explicitement non couverte par la réponse
  (une population particulière non mentionnée) ;
— substitue un acteur par un autre (exemple : le responsable demandé n'est pas
  le même que celui que la réponse cite) ;
— ajoute une condition situationnelle distincte (un régime d'exception, une période
  particulière) dont la réponse ne traite pas ;
— restreint à un sous-domaine que la réponse EXCLUT EXPLICITEMENT ou qui nécessite
  un traitement distinct selon le texte de la réponse elle-même.

Ne réponds PAS INSUFFISANTE pour :
— une reformulation, paraphrase ou synonymie du même concept sans changement de sens ;
— une spécification d'un sous-type que la réponse couvre déjà dans sa généralité,
  à condition que rien dans la réponse ne l'exclue.

Réponds SUFFISANTE seulement si servir cette réponse telle quelle est sans risque.

Ne rédige aucune correction. Réponds uniquement par un objet JSON :
{{"verdict": "SUFFISANTE"}} ou {{"verdict": "INSUFFISANTE"}}"""

# Hypothèse : le juge-ancrage bloque sur des paraphrases car les mots-clés de
# la question ne correspondent pas aux extraits, même quand le sens est le même.
# L'invite modifiée précise qu'une reformulation n'invalide pas l'étayage si
# le contenu factuel de la réponse est bien confirmé par les extraits.

SOURCES_MOD = """Tu contrôles le cache de réponses d'un support interne.

Une réponse DÉJÀ VALIDÉE va être servie à un employé sans qu'aucun humain ne la
relise. Tu dois vérifier qu'elle est ENTIÈREMENT ÉTAYÉE par les documents de
référence POUR LA QUESTION EXACTEMENT POSÉE.

QUESTION POSÉE :
{question}

EXTRAITS DES DOCUMENTS DE RÉFÉRENCE (seule source de vérité admise) :
{sources}

RÉPONSE EN CACHE, celle qu'on servirait :
{cachee}

Réponds NON_ETAYEE si l'un de ces points est vrai :
- un élément factuel de la réponse en cache (montant, délai, acteur, règle) ne
  figure pas dans les extraits ;
- les extraits contredisent la réponse en cache, même partiellement, et en
  particulier sur la polarité (oui / non, autorisé / interdit) ;
- la question porte sur un cas particulier, une condition, une population, une
  période ou une entité dont les extraits ne disent rien. Le silence des documents
  n'autorise JAMAIS à servir : c'est une réponse à donner, pas une lacune à combler.

Réponds ETAYEE si les extraits confirment que la réponse en cache est correcte
et complète pour la question posée. Si la question est une reformulation ou
paraphrase et que les extraits corroborent le contenu factuel de la réponse,
réponds ETAYEE même si le vocabulaire de la question diffère de celui de la réponse
ou des extraits — ce qui compte, c'est que les faits soient étayés, pas que les
mots soient identiques.

N'utilise aucune connaissance extérieure aux extraits. Ne rédige aucune correction.
Réponds uniquement par un objet JSON :
{{"verdict": "ETAYEE"}} ou {{"verdict": "NON_ETAYEE"}}"""

STRATEGIES = {
    "A": "pertinence_orig ET ancrage_orig  (production actuelle)",
    "B": "pertinence_orig seule",
    "C": "ancrage_orig seul",
    "D": "pertinence_MOD ET ancrage_orig",
    "E": "pertinence_orig ET ancrage_MOD",
    "F": "pertinence_MOD ET ancrage_MOD",
}


# ── Indexation ────────────────────────────────────────────────────────────────

def indexer(cas: list[dict], marque: str) -> tuple[dict[str, str], dict[str, dict]]:
    """Indexe documents + réponses canoniques. Retourne (domaines, registre)."""
    domaines = {c["domaine"]: f"{c['domaine']}-{marque}" for c in cas}
    par_doc = {c["doc_source"]: c["domaine"] for c in cas}

    for fichier, dom in sorted(par_doc.items()):
        chemin = DOCS / fichier
        morceaux = chunk_text(extract_text(str(chemin)))
        embeddings = embed_texts(morceaux, is_query=False)
        client.upsert(
            collection_name=COLLECTION_NAME,
            points=[
                PointStruct(
                    id=str(uuid.uuid4()),
                    vector={
                        "dense": e["dense"],
                        "sparse": SparseVector(indices=e["sparse"]["indices"], values=e["sparse"]["values"]),
                    },
                    payload={
                        "doc_id": f"{marque}-{fichier}",
                        "version": 1,
                        "chunk_index": i,
                        "source": fichier,
                        "domaine": domaines[dom],
                        "contenu": m,
                    },
                )
                for i, (m, e) in enumerate(zip(morceaux, embeddings, strict=True))
            ],
            wait=True,
        )

    registre: dict[str, dict] = {}
    textes_can = [c["question_canonique"] for c in cas]
    embs_can = embed_texts(textes_can, is_query=False)
    for c, emb in zip(cas, embs_can, strict=True):
        rid = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{marque}-{c['id']}"))
        client.upsert(
            collection_name=COLLECTION_NAME,
            points=[PointStruct(
                id=rid,
                vector={
                    "dense": emb["dense"],
                    "sparse": SparseVector(indices=emb["sparse"]["indices"], values=emb["sparse"]["values"]),
                },
                payload={"reponse_id": rid, "contenu": c["reponse_canonique"], "domaine": domaines[c["domaine"]]},
            )],
            wait=True,
        )
        registre[rid] = {"contenu": c["reponse_canonique"], "id_cas": c["id"]}

    print(f"  {len(par_doc)} documents, {len(cas)} réponses canoniques indexées.")
    return domaines, registre


def nettoyer(domaines: dict[str, str]) -> None:
    for dom in set(domaines.values()):
        client.delete(
            collection_name=COLLECTION_NAME,
            points_selector=FilterSelector(
                filter=QFilter(must=[FieldCondition(key="domaine", match=MatchValue(value=dom))])
            ),
            wait=True,
        )


# ── Appels LLM ────────────────────────────────────────────────────────────────

def appel(invite: str, attendus: set[str], pause_429: float = 10.0, **champs) -> str | None:
    for tentative in range(5):
        try:
            brut = chat(
                [{"role": "user", "content": invite.format(**champs)}],
                temperature=0, max_tokens=2000, timeout=90,
            )
            m = re.search(r'"verdict"\s*:\s*"(\w+)"', brut or "")
            if m and m.group(1).upper() in attendus:
                return m.group(1).upper()
            return None
        except Exception as e:
            if "429" in str(e) and tentative < 4:
                time.sleep(pause_429 * (tentative + 1))
                continue
            return None
    return None


def juger_k(invite: str, attendus: set[str], k: int, pause: float, **champs) -> list[str | None]:
    verdicts = []
    for i in range(k):
        verdicts.append(appel(invite, attendus, **champs))
        if i < k - 1:
            time.sleep(pause)
    return verdicts


def get_sources(question: str, chunks: list[dict]) -> str:
    utiles = [c for c in chunks if c.get("contenu") and not c.get("reponse_id")]
    if not utiles:
        return ""
    try:
        classes = rerank(question, utiles, top_k=MAX_EXTRAITS)
    except Exception:
        classes = []
    retenus = classes or utiles[:MAX_EXTRAITS]
    return "\n\n".join(f"[extrait {i+1}] {c['contenu']}" for i, c in enumerate(retenus))


# ── Calcul des décisions par stratégie ────────────────────────────────────────

def sert_strat(strat: str, p_orig: list, p_mod: list, a_orig: list, a_mod: list) -> bool | None:
    """None = candidat absent ou juge en échec total (non comptabilisé)."""
    def unanime_suffisante(verdicts): return bool(verdicts) and all(v == "SUFFISANTE" for v in verdicts if v)
    def unanime_etayee(verdicts):    return bool(verdicts) and all(v == "ETAYEE"     for v in verdicts if v)
    def au_moins_un_none(verdicts):  return any(v is None for v in verdicts)

    if strat == "A":
        if au_moins_un_none(p_orig):
            return None
        if not unanime_suffisante(p_orig):
            return False
        if au_moins_un_none(a_orig):
            return None
        return unanime_etayee(a_orig)
    if strat == "B":
        if au_moins_un_none(p_orig):
            return None
        return unanime_suffisante(p_orig)
    if strat == "C":
        if au_moins_un_none(a_orig):
            return None
        return unanime_etayee(a_orig)
    if strat == "D":
        if au_moins_un_none(p_mod):
            return None
        if not unanime_suffisante(p_mod):
            return False
        if au_moins_un_none(a_orig):
            return None
        return unanime_etayee(a_orig)
    if strat == "E":
        if au_moins_un_none(p_orig):
            return None
        if not unanime_suffisante(p_orig):
            return False
        if au_moins_un_none(a_mod):
            return None
        return unanime_etayee(a_mod)
    if strat == "F":
        if au_moins_un_none(p_mod):
            return None
        if not unanime_suffisante(p_mod):
            return False
        if au_moins_un_none(a_mod):
            return None
        return unanime_etayee(a_mod)
    return None


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    parseur = argparse.ArgumentParser()
    parseur.add_argument("--pause", type=float, default=5.0)
    parseur.add_argument("--k", type=int, default=2, help="répétitions par juge (unanimité)")
    parseur.add_argument("--garder-index", action="store_true")
    args = parseur.parse_args()

    cas = json.loads(DATASET.read_text(encoding="utf-8"))["cas"]
    marque = f"AJUST-{uuid.uuid4().hex[:8]}"
    k = args.k

    print(f"\n{'═'*110}")
    print(f"AJUSTEMENT DU GARDE — 6 stratégies × {len(cas)} cas × k={k} répétitions par juge")
    print(f"{'═'*110}")
    print(f"  plancher canonique : {SEUIL_CANDIDAT_CANONIQUE}")
    print(f"  appels LLM max     : {len(cas)} × 4 juges × {k} rép. = {len(cas)*4*k} appels\n")

    print("─ Indexation " + "─"*96)
    domaines, registre = indexer(cas, marque)

    # Matrice de résultats : {id_cas: {strat: bool|None}}
    resultats: dict[str, dict] = {}

    try:
        print(f"\n─ Jugements ({len(cas)} cas) " + "─"*84)

        for c in cas:
            dom = domaines[c["domaine"]]
            chunks = search_hybrid(c["question_variante"], dom, top_k=15)

            # Chercher le candidat canonique
            rid_trouve, contenu_cache, score_trouve = None, None, None
            for ch in chunks:
                rid = str(ch.get("reponse_id") or "")
                if rid and rid in registre and ch["score_cosinus"] >= SEUIL_CANDIDAT_CANONIQUE:
                    rid_trouve, contenu_cache, score_trouve = rid, registre[rid]["contenu"], ch["score_cosinus"]
                    break

            if rid_trouve is None:
                resultats[c["id"]] = dict.fromkeys(STRATEGIES)
                print(f"  {c['id']:<42} cos=-----  candidat absent → toutes stratégies = RAG")
                continue

            sources = get_sources(c["question_variante"], chunks)
            score_str = f"cos={score_trouve:.4f}"

            # Lancer les 4 juges × k répétitions
            p_orig = juger_k(PERTINENCE_ORIG, {"SUFFISANTE","INSUFFISANTE"}, k, args.pause,
                             question=c["question_variante"], reponse=contenu_cache)
            time.sleep(args.pause)
            p_mod  = juger_k(PERTINENCE_MOD,  {"SUFFISANTE","INSUFFISANTE"}, k, args.pause,
                             question=c["question_variante"], reponse=contenu_cache)
            time.sleep(args.pause)
            a_orig = juger_k(SOURCES_ORIG, {"ETAYEE","NON_ETAYEE"}, k, args.pause,
                             question=c["question_variante"], sources=sources, cachee=contenu_cache)
            time.sleep(args.pause)
            a_mod  = juger_k(SOURCES_MOD,  {"ETAYEE","NON_ETAYEE"}, k, args.pause,
                             question=c["question_variante"], sources=sources, cachee=contenu_cache)
            time.sleep(args.pause)

            decisions = {
                s: sert_strat(s, p_orig, p_mod, a_orig, a_mod)
                for s in STRATEGIES
            }
            resultats[c["id"]] = decisions

            def fmt(v): return "SERT" if v else ("RAG " if v is False else "---")
            print(
                f"  {c['id']:<42} {score_str}  "
                f"p_o={p_orig}  p_m={p_mod}  "
                f"a_o={a_orig}  a_m={a_mod}"
            )
            print(
                f"  {'':42}           "
                + "  ".join(f"{s}={fmt(decisions[s])}" for s in STRATEGIES)
                + f"  attendu={'SERT' if c['attendu']=='CACHE' else 'RAG '}"
            )

        # ── Synthèse ──────────────────────────────────────────────────────────
        print(f"\n{'═'*110}")
        print("SYNTHÈSE — par stratégie")
        print(f"{'═'*110}")

        rag_cas   = [c for c in cas if c["attendu"] == "RAG"]
        cache_cas = [c for c in cas if c["attendu"] == "CACHE"]

        print(f"\n  {'Stratégie':<48} {'SERT_À_TORT':>12} {'BLOQUE_À_TORT':>14} {'OK total':>9}  Détail erreurs")
        print("  " + "─"*108)

        gagnants = []
        for strat, desc in STRATEGIES.items():
            sert_tort   = [c for c in rag_cas   if resultats[c["id"]][strat] is True]
            bloque_tort = [c for c in cache_cas  if resultats[c["id"]][strat] is False]

            # Recompte propre
            rag_ok    = sum(1 for c in rag_cas   if resultats[c["id"]][strat] is False)
            cache_ok  = sum(1 for c in cache_cas if resultats[c["id"]][strat] is True)
            absents   = sum(1 for c in cas if resultats[c["id"]][strat] is None)
            ok_total  = rag_ok + cache_ok

            alerte = " ⚠" if sert_tort else ("  ✓" if not bloque_tort else "  →")
            detail = ", ".join(c["id"] for c in sert_tort[:3]) if sert_tort else (
                     ", ".join(c["id"] for c in bloque_tort[:3]) if bloque_tort else "—"
            )
            print(
                f"  {strat} {desc:<43} {len(sert_tort):>12} {len(bloque_tort):>14} "
                f"{ok_total:>4}/{len(cas)-absents:<3}  {detail}{alerte}"
            )
            if not sert_tort:
                gagnants.append((strat, desc, cache_ok, len(bloque_tort)))

        print(f"\n  Stratégies sans SERT_À_TORT ({len(gagnants)}) :")
        gagnants_tri = sorted(gagnants, key=lambda x: -x[2])
        for strat, desc, cache_ok, bloque in gagnants_tri:
            print(f"    {strat} — {cache_ok}/{len(cache_cas)} CACHE corrects, {bloque} blocages à tort | {desc}")

        if gagnants_tri:
            meilleur = gagnants_tri[0]
            print(f"\n  → Meilleure stratégie sûre : {meilleur[0]} ({meilleur[1]})")
            print(f"    {meilleur[2]}/{len(cache_cas)} paraphrases correctement servies, 0 erreur dangereuse.")

        print(
            f"\n  ⚠ k={k} répétitions : un désaccord entre tirages vaut blocage (unanimité).\n"
            f"  IC 95 % ≈ ±30 pts sur {len(cas)} cas. Relancer pour confirmer."
        )

    finally:
        if args.garder_index:
            print(f"\n  Index conservé : {sorted(set(domaines.values()))}")
        else:
            print("\n─ Nettoyage " + "─"*97)
            nettoyer(domaines)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
