"""L'accord RAG↔cache permet-il de servir sans relecture humaine ?

    make up
    PYTHONPATH=. python scripts/eval_accord_rag_cache.py

`eval_cache_over_hit.py` établit que le cosinus classe les cas À L'ENVERS (AUC 0.000) :
une négation ne bouge pas la surface du texte et garde un cosinus de 0.96, une
paraphrase la bouleverse et tombe à 0.71. `eval_garde_fou.py` élimine le rerank
(AUC 0.400). Reste une conception différente, que ce script mesure.

L'IDÉE
------
Aujourd'hui le cache tranche « est-ce la MÊME QUESTION ? » — une équivalence
sémantique ouverte, précisément ce que le cosinus ne sait pas faire. On remplace par
une question bien plus facile : « ces deux RÉPONSES disent-elles la même chose ? »

    question ─┬─ RAG complet (retrieval + rerank + génération) → réponse FRAÎCHE
              └─ cosinus → candidat canonique                  → réponse CACHÉE
                            accord ? ──── OUI → on sert la CACHÉE, zéro humain
                                     └─── NON → revue humaine (flux actuel)

On sert la réponse CACHÉE, pas la fraîche : c'est celle dont le texte a été relu par
un humain. La fraîche n'est qu'un ARBITRE, elle n'est jamais publiée telle quelle.

POURQUOI ÇA PEUT VALOIR LE COÛT
-------------------------------
Le cache de TicketAI n'existe pas pour économiser des tokens, mais pour économiser
un VALIDATEUR HUMAIN. Dépenser une génération RAG pour supprimer une relecture est
donc un bon échange, alors même que ça paraît absurde du point de vue du GPU.
Corollaire : le cosinus cesse d'être le mécanisme de sécurité et redevient un simple
sélecteur de candidat — il pourra être abaissé sans risque.

CE QUI EST MESURÉ
-----------------
Les trois conceptions, sur le même jeu et dans la même session (important : Albert
n'est pas reproductible entre sessions, cf. `eval_juge_modeles.py`) :

    [1] SEUIL COSINUS SEUL       — la production d'aujourd'hui
    [2] JUGE question ↔ réponse  — le garde-fou de `eval_garde_fou.py`
    [3] ACCORD rag ↔ cache       — la conception proposée

HYPOTHÈSE À FALSIFIER : [3] attrape `nikon-mail-non-marque` (le RAG frais, interrogé
sur la question niée, doit répondre l'inverse du cache) ET `teletravail-indemnite-
alternant` (aucun des 4 documents ne contient « alternant » : le RAG doit répondre
HORS_DOMAINE) — les deux cas qui mettent [1] et [2] en défaut.

Opt-in : nécessite Qdrant (`make up`) et consomme des tokens Albert
(indexation des 4 documents + 8 × (recherche + rerank + génération + 2 jugements)).
Aucune écriture en base : ce script ne touche pas Postgres.
"""

import argparse
import json
import math
import re
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, ".")

from app.config import settings
from app.services.embedding import embed_texts
from app.services.llm import chat, generate
from app.services.qdrant import COLLECTION_NAME, client
from app.services.reranker import rerank
from app.services.search import search_hybrid
from app.workers.ingestion import chunk_text, extract_text
from qdrant_client.models import FieldCondition, FilterSelector, MatchValue, PointStruct, SparseVector
from qdrant_client.models import Filter as QFilter

RACINE = Path(__file__).resolve().parent.parent
DATASET = RACINE / "tests" / "dataset_precision.json"
DOCS = RACINE / "tests"

# Le modèle en service. `eval_juge_modeles.py` a écarté Ministral-3-8B (verdict
# constant) et Mistral-Small-24B (une erreur dangereuse de plus).
JUGE = "openai/gpt-oss-120b"

VERDICTS_ACCORD = {"IDENTIQUE", "DIVERGENTE"}
VERDICTS_PERTINENCE = {"SUFFISANTE", "INSUFFISANTE"}
VERDICTS_SOURCES = {"ETAYEE", "NON_ETAYEE"}

# ── [3] la conception proposée ───────────────────────────────────────────────
# La consigne compare deux RÉPONSES, jamais la question à une réponse. C'est une
# tâche d'implication textuelle (« B ajoute-t-il quelque chose que A tait ? »),
# bien mieux définie que l'équivalence de questions — et c'est tout l'intérêt.
INVITE_ACCORD = """Tu contrôles le cache de réponses d'un support interne.

Une réponse DÉJÀ VALIDÉE par un humain est sur le point d'être servie sans nouvelle
relecture. En parallèle, le moteur documentaire vient de rédiger une réponse FRAÎCHE
à la question posée, à partir des documents de référence.

QUESTION POSÉE :
{question}

RÉPONSE A — en cache, validée, celle qu'on servirait :
{cachee}

RÉPONSE B — fraîche, rédigée à l'instant depuis les documents de référence :
{fraiche}

B fait autorité sur le CONTENU. A fait autorité sur la FORMULATION.

Servir A à la place de B tromperait-il le lecteur ?

Réponds DIVERGENTE si :
- A affirme quelque chose que B contredit, même partiellement, et en particulier si
  la polarité (oui / non, autorisé / interdit) n'est pas la même ;
- B mentionne une condition, une restriction, un cas particulier, un montant, un
  délai, une entité ou un destinataire que A ne mentionne pas ;
- B indique que les documents ne traitent pas ce cas alors que A répond affirmativement.

Réponds IDENTIQUE seulement si A et B véhiculent la même information utile, aux
différences de style et de longueur près.

Ne rédige aucune correction. Réponds uniquement par un objet JSON :
{{"verdict": "IDENTIQUE"}} ou {{"verdict": "DIVERGENTE"}}"""

# ── [6] l'ancrage : juger contre les SOURCES, sans génération dans la boucle ─
# Motivé par un échec mesuré de [3] : sur `teletravail-indemnite-alternant`, le RAG
# frais a HALLUCINÉ « y compris un alternant en contrat d'apprentissage », phrase
# absente des documents. Le juge d'accord a alors correctement constaté que les deux
# textes concordaient — et a servi une réponse fausse. Tant qu'un texte GÉNÉRÉ sert
# d'arbitre, la sûreté du cache est plafonnée par le taux d'hallucination du RAG.
# Ici le juge ne voit aucun texte généré : seulement la question, les extraits
# réellement indexés, et la réponse en cache.
INVITE_SOURCES = """Tu contrôles le cache de réponses d'un support interne.

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

# ── [2] la référence, reprise mot pour mot d'`eval_garde_fou.py` ─────────────
# Recopiée volontairement plutôt qu'importée : les deux consignes doivent pouvoir
# évoluer séparément, et une comparaison n'a de sens que si la référence est figée.
INVITE_PERTINENCE = """Tu es un contrôleur qualité d'un support interne.

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


def cosinus(a: list[float], b: list[float]) -> float:
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    return sum(x * y for x, y in zip(a, b, strict=True)) / (na * nb)


def juger(invite: str, attendus: set[str], **champs) -> str:
    """Un appel température 0, repli sûr vers INCERTAIN.

    `max_tokens` est large à dessein : le modèle en service est un modèle À
    RAISONNEMENT, il consomme son budget de sortie dans un champ `reasoning` avant
    d'émettre le moindre `content`. À 64 tokens il rendait 8 verdicts vides sur 8.
    """
    for tentative in range(5):
        try:
            brut = chat(
                [{"role": "user", "content": invite.format(**champs)}],
                temperature=0,
                max_tokens=2000,
                timeout=180,
            )
            break
        except Exception as erreur:  # noqa: BLE001 — une panne Albert doit bloquer, pas planter
            if "429" in str(erreur) and tentative < 4:
                time.sleep(10 * (tentative + 1))
                continue
            print(f"    (échec Albert : {str(erreur)[:120]})")
            return "INCERTAIN"
    else:
        return "INCERTAIN"

    trouve = re.search(r'"verdict"\s*:\s*"(\w+)"', brut or "")
    if trouve and trouve.group(1).upper() in attendus:
        return trouve.group(1).upper()
    return "INCERTAIN"


def juger_repete(invite: str, attendus: set[str], k: int, pause: float, **champs) -> list[str]:
    """Interroge le même juge `k` fois. Renvoie les `k` verdicts, dans l'ordre.

    `temperature=0` NE garantit PAS la reproductibilité chez Albert : cinq mesures
    de gpt-oss sur ce jeu ont donné 7/8 quatre fois et 5/8 une fois, à code
    identique (`eval_juge_modeles.py`). C'est une faiblesse tant qu'on tire une
    seule fois — ça devient un instrument dès qu'on tire plusieurs fois et qu'on
    exige l'UNANIMITÉ pour servir : un cas où le modèle hésite se trahit par un
    désaccord entre tirages, et l'hésitation vaut blocage.

    L'unanimité, et non la majorité, pour la même raison que le ET de [4] : bloquer
    à tort ne coûte qu'un retour au flux RAG normal.
    """
    verdicts = []
    for i in range(k):
        verdicts.append(juger(invite, attendus, **champs))
        if i < k - 1:
            time.sleep(pause)
    return verdicts


def indexer(cas: list[dict], marque: str) -> dict[str, str]:
    """Indexe les documents du jeu via le VRAI chemin d'ingestion.

    Isolation par `domaine` suffixé : `search_hybrid` filtre sur `domaine`, donc la
    lecture ne peut pas voir le corpus de développement — et la cardinalité filtrée
    passe sous le `full_scan_threshold` de Qdrant, qui bascule en recherche exacte
    (pas d'aléa de rappel HNSW).

    Le vrai `extract_text` + `chunk_text` sont réutilisés : chunker autrement ici
    mesurerait un pipeline que la production n'a jamais exécuté.
    """
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
                        "sparse": SparseVector(indices=emb["sparse"]["indices"], values=emb["sparse"]["values"]),
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
        print(f"  {fichier:<48} {len(morceaux):>3} chunks → domaine {domaines[domaine_reel]}")
    return domaines


def nettoyer(domaines: dict[str, str]) -> None:
    """Purge par filtre sur le domaine, `wait=True`. Doit tourner même après un échec."""
    for domaine in set(domaines.values()):
        client.delete(
            collection_name=COLLECTION_NAME,
            points_selector=FilterSelector(
                filter=QFilter(must=[FieldCondition(key="domaine", match=MatchValue(value=domaine))])
            ),
            wait=True,
        )
    print(f"\n  Nettoyage : {len(set(domaines.values()))} domaines de test purgés.")


def generer_avec_reprise(question: str, chunks: list[dict]) -> tuple[str, bool, bool]:
    """Renvoie (texte, hors_domaine, mesure_valide).

    Le troisième drapeau existe pour une raison précise : un 429 d'Albert ne doit
    PAS se lire comme un HORS_DOMAINE. Les deux bloqueraient le service, donc la
    conception paraîtrait prudente — alors qu'on aurait mesuré le quota, pas le
    pipeline. Un run précédent a produit exactement cette illusion sur
    `onboarding-sla-reformule`. Une mesure ratée doit être déclarée ratée et sortie
    des comptes, jamais recyclée en verdict.
    """
    for tentative in range(5):
        try:
            texte, hors_domaine = generate(question, chunks)
            return texte, hors_domaine, True
        except Exception as erreur:  # noqa: BLE001
            if "429" in str(erreur) and tentative < 4:
                attente = 15 * (tentative + 1)
                print(f"    (429 sur la génération, reprise dans {attente}s)")
                time.sleep(attente)
                continue
            print(f"    (génération en échec : {str(erreur)[:110]})")
            return "", False, False
    return "", False, False


def bilan(cas: list[dict], cle: str) -> dict:
    """Compte les erreurs SANS les moyenner : les deux sens n'ont pas le même coût."""
    rag = [c for c in cas if c["attendu"] == "RAG"]
    justes = sum(1 for c in cas if c[cle] == (c["attendu"] == "CACHE"))
    dangereux = [c for c in rag if c[cle]]
    return {
        "justes": justes,
        "dangereux": [c["id"] for c in dangereux],
        "critiques": [c["id"] for c in dangereux if c["gravite"] == "CRITIQUE"],
        "prudents": [c["id"] for c in cas if c["attendu"] == "CACHE" and not c[cle]],
    }


def main() -> int:
    parseur = argparse.ArgumentParser()
    parseur.add_argument("--pause", type=float, default=6.0, help="respiration entre appels (429)")
    parseur.add_argument("--seuil", type=float, default=settings.seuil_cosinus)
    parseur.add_argument("--garder-index", action="store_true", help="ne pas purger Qdrant en sortie")
    parseur.add_argument("--repetitions", type=int, default=3, help="tirages par juge pour [5] (unanimité)")
    args = parseur.parse_args()

    cas = json.loads(DATASET.read_text(encoding="utf-8"))["cas"]
    marque = f"ACCORD-{uuid.uuid4().hex[:8]}"

    print(f"\n{'═' * 100}")
    print("ACCORD RAG ↔ CACHE — peut-on servir sans relecture humaine ?")
    print(f"{'═' * 100}")
    print(f"\n  modèle juge        : {JUGE}")
    print(f"  modèle embeddings  : {settings.albert_embeddings_model_name}")
    print(f"  seuil cosinus      : {args.seuil}")
    print(f"  cas                : {len(cas)}\n")

    print("─ Indexation des documents de référence " + "─" * 60)
    domaines = indexer(cas, marque)

    try:
        # ── [1] la production d'aujourd'hui : le cosinus des questions ───────
        textes = [t for c in cas for t in (c["question_canonique"], c["question_variante"])]
        vecteurs = [e["dense"] for e in embed_texts(textes)]
        for i, c in enumerate(cas):
            c["cos_paire"] = cosinus(vecteurs[2 * i], vecteurs[2 * i + 1])
            c["sert_seuil"] = c["cos_paire"] >= args.seuil

        # ── [2] et [3] ──────────────────────────────────────────────────────
        print("\n─ RAG frais + jugements " + "─" * 76)
        for c in cas:
            domaine = domaines[c["domaine"]]
            chunks = search_hybrid(c["question_variante"], domaine, top_k=15)
            chunks = rerank(c["question_variante"], chunks, top_k=5) or chunks[:5]
            fraiche, hors_domaine, valide = generer_avec_reprise(c["question_variante"], chunks)
            c["fraiche"], c["hors_domaine"], c["echec"] = fraiche, hors_domaine, not valide

            # Raccourci STRUCTUREL, pas un jugement de modèle : si les documents ne
            # traitent pas le cas, aucune réponse en cache ne peut le traiter non
            # plus. Zéro appel LLM, zéro variance — et c'est ce qui doit attraper
            # `teletravail-indemnite-alternant`.
            if not valide:
                c["accord"], c["accords_k"] = "ÉCHEC", []
            elif hors_domaine:
                c["accord"], c["accords_k"] = "HORS_DOMAINE", []
            else:
                c["accords_k"] = juger_repete(
                    INVITE_ACCORD,
                    VERDICTS_ACCORD,
                    args.repetitions,
                    args.pause,
                    question=c["question_variante"],
                    cachee=c["reponse_canonique"],
                    fraiche=fraiche,
                )
                c["accord"] = c["accords_k"][0]
                time.sleep(args.pause)
            c["sert_accord"] = c["accord"] == "IDENTIQUE"

            c["pertinences_k"] = juger_repete(
                INVITE_PERTINENCE,
                VERDICTS_PERTINENCE,
                args.repetitions,
                args.pause,
                question=c["question_variante"],
                reponse=c["reponse_canonique"],
            )
            c["pertinence"] = c["pertinences_k"][0]
            c["sert_pertinence"] = c["pertinence"] == "SUFFISANTE"
            time.sleep(args.pause)

            # [4] — la conjonction. Aucun appel supplémentaire : c'est de la logique
            # sur des verdicts déjà payés. Le ET (et pas le OU) est imposé par
            # l'asymétrie des coûts : bloquer à tort ne fait que rendre la main au
            # RAG, donc il faut l'unanimité pour se passer d'un humain. Et les deux
            # signaux sont indépendants par construction — [2] n'a jamais vu les
            # documents, [3] n'a jamais vu la question canonique.
            c["sert_conjonction"] = c["sert_pertinence"] and c["sert_accord"]

            # [5] — la même conjonction, mais chaque juge doit être unanime sur ses
            # k tirages. Un désaccord entre tirages est une hésitation du modèle, et
            # l'hésitation vaut blocage. `hors_domaine` reste un blocage structurel.
            unanime_a = bool(c["accords_k"]) and all(v == "IDENTIQUE" for v in c["accords_k"])
            unanime_p = all(v == "SUFFISANTE" for v in c["pertinences_k"])
            c["sert_unanime"] = unanime_a and unanime_p
            c["hesite"] = len(set(c["accords_k"])) > 1 or len(set(c["pertinences_k"])) > 1

            # [6] — ancrage sur les sources. Les extraits soumis sont EXACTEMENT ceux
            # que le RAG a utilisés pour générer, donc [6] et [3] voient la même
            # information : seule la présence d'un texte généré dans la boucle change.
            sources = "\n\n".join(f"[extrait {i + 1}] {ch['contenu']}" for i, ch in enumerate(chunks))
            c["sources_verdict"] = juger(
                INVITE_SOURCES,
                VERDICTS_SOURCES,
                question=c["question_variante"],
                sources=sources,
                cachee=c["reponse_canonique"],
            )
            c["sert_sources"] = c["sources_verdict"] == "ETAYEE"
            time.sleep(args.pause)

            # [7] — la conjonction la plus stricte qui n'implique aucune génération
            # dans le chemin de sécurité.
            c["sert_strict"] = c["sert_pertinence"] and c["sert_sources"]

            attendu_sert = c["attendu"] == "CACHE"
            marque_3 = "ÉCHEC" if c["echec"] else ("SERT" if c["sert_accord"] else "rag ")
            alerte = "" if c["echec"] else ("  ⚠" if c["sert_unanime"] != attendu_sert else "")
            print(
                f"  {c['id']:<34} cos {c['cos_paire']:.4f} "
                f"[1]{'SERT' if c['sert_seuil'] else 'rag ':<5} "
                f"[2]{'SERT' if c['sert_pertinence'] else 'rag ':<5} "
                f"[3]{marque_3:<5} "
                f"[4]{'SERT' if c['sert_conjonction'] else 'rag ':<5} "
                f"[5]{'SERT' if c['sert_unanime'] else 'rag ':<5} "
                f"[6]{'SERT' if c['sert_sources'] else 'rag ':<5} "
                f"[7]{'SERT' if c['sert_strict'] else 'rag ':<5} "
                f"{'hésite' if c['hesite'] else '      '} "
                f"attendu {'SERT' if attendu_sert else 'rag'}" + alerte
            )

        # ── Synthèse ────────────────────────────────────────────────────────
        # Les cas dont la génération a échoué sortent des TROIS colonnes, pas
        # seulement de [3] : comparer des conceptions sur des dénominateurs
        # différents produirait un classement qui reflète le quota Albert.
        valides = [c for c in cas if not c["echec"]]
        rates = [c["id"] for c in cas if c["echec"]]
        conceptions = [
            ("[1] seuil cosinus seul (production d'avant)", "sert_seuil"),
            ("[2] juge question ↔ réponse cachée", "sert_pertinence"),
            ("[3] accord RAG frais ↔ réponse cachée", "sert_accord"),
            ("[4] conjonction [2] ET [3]", "sert_conjonction"),
            (f"[5] conjonction + unanimité sur {args.repetitions} tirages", "sert_unanime"),
            ("[6] ancrage sur les sources (sans génération)", "sert_sources"),
            ("[7] conjonction [2] ET [6]", "sert_strict"),
        ]
        print(f"\n{'═' * 100}\nSYNTHÈSE\n{'═' * 100}")
        if rates:
            print(f"\n  ⚠ MESURES ÉCARTÉES (Albert indisponible, pas un verdict) : {', '.join(rates)}")
        print(f"\n{'conception':<40} {'justes':>7} {'SERT À TORT':>12} {'CRITIQUE':>9} {'bloque à tort':>14}")
        print("-" * 100)
        resultats = {}
        for titre, cle in conceptions:
            b = bilan(valides, cle)
            resultats[cle] = b
            print(
                f"{titre:<40} {b['justes']:>4}/{len(valides):<2} {len(b['dangereux']):>12} "
                f"{len(b['critiques']):>9} {len(b['prudents']):>14}"
            )

        print(
            "\n  « SERT À TORT » est la seule colonne qui compte vraiment : elle expose une\n"
            "  réponse fausse estampillée VALIDÉE, sans validateur. « bloque à tort » ne fait\n"
            "  que rendre la main au RAG — c'est-à-dire au comportement actuel du produit."
        )

        def extrait(c: dict) -> str:
            return " ".join((c["fraiche"] or "(vide)").split())[:260]

        for titre, cle in conceptions:
            b = resultats[cle]
            if b["dangereux"]:
                print(f"\n  {titre}\n      sert à tort : {', '.join(b['dangereux'])}")

        # Chaque cas servi à tort par [3] est un désaccord que le juge n'a pas vu :
        # sans la réponse fraîche sous les yeux, impossible de savoir si la faute
        # vient du juge ou d'un RAG qui a reproduit l'erreur du cache.
        if resultats["sert_accord"]["dangereux"]:
            print(f"\n{'─' * 100}\n[3] — CE QUE LE RAG FRAIS AVAIT RÉPONDU SUR LES CAS SERVIS À TORT\n{'─' * 100}")
            for cid in resultats["sert_accord"]["dangereux"]:
                c = next(x for x in valides if x["id"] == cid)
                print(f"\n  {cid}  (gravité {c['gravite']})")
                print(f"    en cache : {' '.join(c['reponse_canonique'].split())[:260]}")
                print(f"    fraîche  : {extrait(c)}")

        # Le gain net se lit sur les deux cas que [1] et [2] ratent.
        print(f"\n{'─' * 100}\nLES DEUX CAS DÉCISIFS\n{'─' * 100}")
        for cible in ("nikon-mail-non-marque", "teletravail-indemnite-alternant"):
            c = next(x for x in cas if x["id"] == cible)
            print(f"\n  {cible}  (gravité {c['gravite']}, attendu RAG)")
            print(f"    [1] cosinus {c['cos_paire']:.4f} → {'SERT ✗' if c['sert_seuil'] else 'rag ✓'}")
            print(f"    [2] {c['pertinence']:<13} → {'SERT ✗' if c['sert_pertinence'] else 'rag ✓'}")
            print(f"    [3] {c['accord']:<13} → {'SERT ✗' if c['sert_accord'] else 'rag ✓'}")
            print(f"    réponse fraîche du RAG : {extrait(c)}…")

        hd = [c["id"] for c in valides if c["hors_domaine"]]
        print(
            f"\n  Bloqués par le raccourci HORS_DOMAINE (aucun appel LLM, aucune variance) : "
            f"{', '.join(hd) if hd else 'aucun'}"
        )

        # C'est le chiffre qui dit si [5] apporte quelque chose ou si on paie k fois
        # pour rien : sans désaccord entre tirages, [5] est identique à [4].
        hesitants = [c for c in valides if c["hesite"]]
        print(f"\n{'─' * 100}\nCE QUE L'UNANIMITÉ RÉVÈLE ({args.repetitions} tirages par juge)\n{'─' * 100}")
        print(f"\n  cas où les tirages divergent : {len(hesitants)}/{len(valides)}")
        for c in hesitants:
            bascule = " ← bascule le verdict" if c["sert_conjonction"] != c["sert_unanime"] else ""
            print(
                f"    {c['id']:<34} attendu {'SERT' if c['attendu'] == 'CACHE' else 'rag ':<5}"
                f"  accord {c['accords_k'] or ['—']}  pertinence {c['pertinences_k']}{bascule}"
            )
        if not hesitants:
            print("    (aucun — sur ce run, [5] est strictement équivalent à [4])")
        print(
            f"\n  ⚠ {len(valides)} cas mesurés : IC 95 % de ±35 points. Ce tableau sert à éliminer\n"
            "  une conception, pas à publier un taux. Et `temperature=0` n'est pas reproductible\n"
            "  chez Albert (cf. eval_juge_modeles.py) : répéter avant de trancher."
        )
    finally:
        if args.garder_index:
            print(f"\n  Index CONSERVÉ (--garder-index) : domaines {sorted(set(domaines.values()))}")
        else:
            nettoyer(domaines)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
