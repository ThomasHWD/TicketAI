"""Mesure du Cache Over-Hit sur de vrais embeddings Albert.

    PYTHONPATH=. python scripts/eval_cache_over_hit.py
    PYTHONPATH=. python scripts/eval_cache_over_hit.py --json | jq .

Les tests de `tests/test_cache_over_hit*.py` prouvent *où* le cache peut se
tromper, avec des cosinus fabriqués. Ils ne disent rien de la fréquence réelle :
pour ça il faut savoir à quelle distance BGE-M3 place réellement une question
générique de sa version précisée. C'est ce que ce script mesure — et c'est
pourquoi il est **opt-in** : il consomme des tokens Albert et ne tourne pas en CI.

**Ce script ne teste rien, il instrumente.** Il n'échoue pas sur un mauvais
chiffre ; il l'imprime. La décision (relever le seuil, ressusciter le sparse,
interdire CANONIQUE sur les questions de suivi) se prend sur le rapport, pas ici.

Discipline d'import : seuls `app.config` et `app.services.embedding` sont
importés. Aucune base, aucun Qdrant, aucun effet de bord — le rapport JSON part
sur stdout pour rester pipeable.
"""

import argparse
import json
import math
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, ".")

from app.config import settings
from app.services.embedding import embed_texts

# Le script doit rester lisible sans base : aucune connexion ne doit s'ouvrir,
# ni ici ni par un import transitif. L'assert échoue bruyamment si quelqu'un
# ajoute un import qui tire `app.database` dans son sillage.
assert "app.database" not in sys.modules, (
    "app.database a été importé : ce script doit rester sans effet de bord (aucune connexion DB)."
)

RACINE = Path(__file__).resolve().parent.parent
DATASET = RACINE / "tests" / "dataset_precision.json"
CORPUS_MD = RACINE / "tests"

# Une réponse juridiquement inversée n'est pas la même faute qu'une réponse un peu
# trop générique. Le taux brut les compte pareil ; le taux pondéré, non.
POIDS_GRAVITE = {"CRITIQUE": 3, "MAJEURE": 2, "MINEURE": 1}


# ══════════════════════════════════════════════════════════════════════════════
# Statistiques
# ══════════════════════════════════════════════════════════════════════════════


def cosinus(a: list[float], b: list[float]) -> float:
    """Cosinus explicite : Albert ne garantit pas de renvoyer des vecteurs unitaires."""
    ps = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    return ps / (na * nb) if na and nb else 0.0


def wilson(succes: int, total: int, z: float = 1.96) -> tuple[float, float]:
    """Intervalle de Wilson à 95 %.

    Pas l'intervalle normal : sur 5 échantillons, avec des taux qui frôlent 0 ou
    1, l'approximation normale produit des bornes hors de [0, 1] et une largeur
    nulle à 0 % — elle affirmerait une certitude qu'on n'a pas. Wilson reste
    honnête aux petits effectifs, ce qui est exactement le régime de ce dataset.
    """
    if total == 0:
        return (0.0, 0.0)
    p = succes / total
    d = 1 + z**2 / total
    centre = (p + z**2 / (2 * total)) / d
    demi = z * math.sqrt(p * (1 - p) / total + z**2 / (4 * total**2)) / d
    return (max(0.0, centre - demi), min(1.0, centre + demi))


def auc(scores_positifs: list[float], scores_negatifs: list[float]) -> float:
    """AUC = P(score positif > score négatif), via la statistique de Mann-Whitney.

    Calculée à la main plutôt qu'avec `roc_auc_score` pour rester définie quand
    une classe est vide (renvoie alors 0.5) — cas courant après un `--limit`.
    """
    if not scores_positifs or not scores_negatifs:
        return 0.5
    gains = sum(1.0 if p > n else 0.5 if p == n else 0.0 for p in scores_positifs for n in scores_negatifs)
    return gains / (len(scores_positifs) * len(scores_negatifs))


def barre(valeur: float, largeur: int = 24) -> str:
    plein = round(valeur * largeur)
    return "█" * plein + "·" * (largeur - plein)


# ══════════════════════════════════════════════════════════════════════════════
# Contrefactuel lexical — TF-IDF / BM25 maison
# ══════════════════════════════════════════════════════════════════════════════

_MOT = re.compile(r"\w+", re.UNICODE)


def tokeniser(texte: str) -> list[str]:
    return _MOT.findall(texte.lower())


def idf_du_corpus(documents: list[list[str]]) -> dict[str, float]:
    """IDF lissé, sur les 4 documents métier + toutes les questions du dataset."""
    n = len(documents)
    freq_doc: dict[str, int] = defaultdict(int)
    for doc in documents:
        for terme in set(doc):
            freq_doc[terme] += 1
    return {t: math.log(1 + (n - c + 0.5) / (c + 0.5)) for t, c in freq_doc.items()}


def bm25(
    requete: list[str], document: list[str], idf: dict[str, float], avgdl: float, k1: float = 1.5, b: float = 0.75
) -> float:
    """BM25 standard — le signal lexical que la jambe sparse morte devrait fournir."""
    if not document:
        return 0.0
    tf: dict[str, int] = defaultdict(int)
    for terme in document:
        tf[terme] += 1
    norme = k1 * (1 - b + b * len(document) / avgdl) if avgdl else k1
    return sum(idf.get(t, 0.0) * (tf[t] * (k1 + 1)) / (tf[t] + norme) for t in requete if t in tf)


# ══════════════════════════════════════════════════════════════════════════════
# Rapport
# ══════════════════════════════════════════════════════════════════════════════


def titre(texte: str) -> None:
    print(f"\n{'═' * 78}\n{texte}\n{'═' * 78}")


def section_paires(cas: list[dict], seuil: float) -> None:
    titre("[1] PAIRES — cos(question_canonique, question_variante)")
    print(f"\n{'cos':>7}  {'verdict':<12} {'gravité':<9} {'taxonomie':<24} id")
    print(f"{'-' * 78}")
    for c in sorted(cas, key=lambda x: -x["cosinus"]):
        sert = c["cosinus"] >= seuil
        if c["attendu"] == "RAG":
            verdict = "OVER-HIT ✗" if sert else "ok"
        else:
            verdict = "ok" if sert else "UNDER-HIT ✗"
        print(f"{c['cosinus']:>7.4f}  {verdict:<12} {c['gravite'] or '—':<9} {c['taxonomie']:<24} {c['id']}")


def section_confusion(cas: list[dict], seuil: float) -> dict:
    titre(f"[2] MATRICE DE CONFUSION @ seuil = {seuil}")

    rag = [c for c in cas if c["attendu"] == "RAG"]
    cache = [c for c in cas if c["attendu"] == "CACHE"]
    over = [c for c in rag if c["cosinus"] >= seuil]
    under = [c for c in cache if c["cosinus"] < seuil]

    taux_over = len(over) / len(rag) if rag else 0.0
    taux_under = len(under) / len(cache) if cache else 0.0
    bas_o, haut_o = wilson(len(over), len(rag))
    bas_u, haut_u = wilson(len(under), len(cache))

    print(f"\n{'':22} {'servi par le cache':>20} {'passé au RAG':>16}")
    print(f"{'-' * 78}")
    print(f"{'devrait aller au RAG':22} {len(over):>20} {len(rag) - len(over):>16}   ← over-hit")
    print(f"{'peut venir du cache':22} {len(cache) - len(under):>20} {len(under):>16}   ← under-hit")

    print(f"\n  over-hit  : {taux_over:6.1%}  [{bas_o:.1%} – {haut_o:.1%}]  {len(over)}/{len(rag)}")
    print(f"  under-hit : {taux_under:6.1%}  [{bas_u:.1%} – {haut_u:.1%}]  {len(under)}/{len(cache)}")

    poids_total = sum(POIDS_GRAVITE.get(c["gravite"], 1) for c in rag)
    poids_rate = sum(POIDS_GRAVITE.get(c["gravite"], 1) for c in over)
    pondere = poids_rate / poids_total if poids_total else 0.0
    print(f"\n  over-hit pondéré par la gravité (CRITIQUE=3, MAJEURE=2, MINEURE=1) : {pondere:6.1%}")
    critiques = [c for c in over if c["gravite"] == "CRITIQUE"]
    if critiques:
        print(f"  dont CRITIQUE servi sans revue : {', '.join(c['id'] for c in critiques)}")

    print(
        "\n  Les intervalles de Wilson valent lecture avant les taux : à cet effectif\n"
        "  ils couvrent la moitié de l'échelle. Ce rapport indique une direction,\n"
        "  il ne mesure pas encore un taux."
    )
    return {
        "over_hit": taux_over,
        "under_hit": taux_under,
        "over_hit_pondere": pondere,
        "ic_over_hit": [bas_o, haut_o],
        "ic_under_hit": [bas_u, haut_u],
        "ids_over_hit": [c["id"] for c in over],
        "ids_under_hit": [c["id"] for c in under],
    }


def section_taxonomie(cas: list[dict], seuil: float) -> dict:
    titre("[3] PAR TAXONOMIE")
    groupes: dict[str, list[dict]] = defaultdict(list)
    for c in cas:
        groupes[c["taxonomie"]].append(c)

    print(f"\n{'taxonomie':<24} {'n':>3} {'cos moy':>8} {'min':>7} {'max':>7} {'over-hit':>9}")
    print(f"{'-' * 78}")
    resultat = {}
    for nom, grp in sorted(groupes.items(), key=lambda kv: -sum(c["cosinus"] for c in kv[1]) / len(kv[1])):
        cosinus_grp = [c["cosinus"] for c in grp]
        rag = [c for c in grp if c["attendu"] == "RAG"]
        over = [c for c in rag if c["cosinus"] >= seuil]
        taux = f"{len(over) / len(rag):.0%}" if rag else "—"
        moy = sum(cosinus_grp) / len(cosinus_grp)
        print(f"{nom:<24} {len(grp):>3} {moy:>8.4f} {min(cosinus_grp):>7.4f} {max(cosinus_grp):>7.4f} {taux:>9}")
        resultat[nom] = {"n": len(grp), "cos_moyen": moy, "over_hit": len(over) / len(rag) if rag else None}

    mixtes = [n for n, g in groupes.items() if len({c["attendu"] for c in g}) > 1]
    if mixtes:
        print(
            f"\n  ⚠ Taxonomie(s) portant les DEUX étiquettes : {', '.join(mixtes)}.\n"
            "  Deux questions de forme syntaxique identique, l'une devant aller au RAG,\n"
            "  l'autre pouvant venir du cache : aucune règle sur la forme seule ne les\n"
            "  sépare. C'est le cœur du problème, pas une anomalie du dataset."
        )
    return resultat


def section_balayage(cas: list[dict]) -> dict:
    titre("[4] BALAYAGE DU SEUIL")
    rag = [c for c in cas if c["attendu"] == "RAG"]
    cache = [c for c in cas if c["attendu"] == "CACHE"]

    print(f"\n{'seuil':>6} {'over-hit':>9} {'under-hit':>10} {'somme':>7} {'J':>7}   over-hit")
    print(f"{'-' * 78}")
    lignes, meilleur = [], None
    for i in range(80, 99):
        s = i / 100
        o = sum(1 for c in rag if c["cosinus"] >= s) / len(rag) if rag else 0.0
        u = sum(1 for c in cache if c["cosinus"] < s) / len(cache) if cache else 0.0
        j = (1 - o) + (1 - u) - 1  # Youden : sensibilité + spécificité − 1
        lignes.append({"seuil": s, "over_hit": o, "under_hit": u, "somme": o + u, "youden": j})
        if meilleur is None or j > meilleur["youden"]:
            meilleur = lignes[-1]
        marque = " ←" if abs(s - settings.seuil_candidat_canonique) < 1e-9 else ""
        print(f"{s:>6.2f} {o:>9.1%} {u:>10.1%} {o + u:>7.2f} {j:>7.2f}   {barre(o)}{marque}")

    print(
        f"\n  Planchers de candidature en service : "
        f"{settings.seuil_candidat_canonique:.2f} (canonique) · "
        f"{settings.seuil_suggestion:.2f} (validée non canonique)"
    )
    print(
        "  Rappel : aucun de ces planchers ne décide plus du service SANS REVUE — ils ne\n"
        "  font que désigner un candidat, que le garde (deux juges LLM) doit approuver.\n"
        "  Le tableau ci-dessus mesure donc ce qu'un seuil scalaire *pourrait* trancher\n"
        "  seul ; sa conclusion mesurée est qu'aucun ne le peut."
    )
    print(
        f"  Meilleur J de Youden : seuil {meilleur['seuil']:.2f} "
        f"(over-hit {meilleur['over_hit']:.0%}, under-hit {meilleur['under_hit']:.0%})"
    )
    if meilleur["somme"] > 0:
        print(
            "\n  Aucun seuil n'annule les deux erreurs : les deux populations se\n"
            "  chevauchent, et le curseur ne fait que choisir laquelle subir."
        )
    return {"courbe": lignes, "meilleur_youden": meilleur}


def section_separabilite(cas: list[dict]) -> dict:
    titre("[5] SÉPARABILITÉ — un seuil scalaire est-il viable ?")
    rag = [c["cosinus"] for c in cas if c["attendu"] == "RAG"]
    cache = [c["cosinus"] for c in cas if c["attendu"] == "CACHE"]
    if not rag or not cache:
        print("\n  Une des deux polarités est vide (--limit ?) — section non calculable.")
        return {}

    marge = min(cache) - max(rag)
    aire = auc(cache, rag)  # « positif » = doit venir du cache
    print(f"\n  max(cos) des paires devant aller au RAG : {max(rag):.4f}")
    print(f"  min(cos) des paires pouvant venir du cache : {min(cache):.4f}")
    print(f"  marge : {marge:+.4f}")
    print(f"  AUC (cosinus seul) : {aire:.3f}")
    if marge > 0:
        print(
            f"\n  VERDICT : populations séparables sur ce dataset. Tout seuil dans\n"
            f"  ]{max(rag):.4f}, {min(cache):.4f}] classe les 8 cas correctement.\n"
            "  À ne pas lire comme « le cache est sûr » : 8 paires choisies à la main\n"
            "  ne couvrent pas l'espace des questions, et le §7 montre que le score\n"
            "  effectif en production est supérieur au cosinus par paire."
        )
    else:
        print(
            "\n  VERDICT : populations NON séparables. Il existe une paire devant aller\n"
            "  au RAG plus proche que la paire la plus lointaine servie par le cache :\n"
            "  aucun seuil sur le cosinus seul ne peut être correct partout. Le\n"
            "  correctif doit ajouter un signal, pas déplacer le curseur."
        )

    if aire <= 0.25:
        print(
            f"\n  ⚠ LIRE CET AVERTISSEMENT AVANT DE CITER L'AUC ({aire:.3f}).\n"
            "  Une AUC proche de 0 dit que le cosinus classe à l'ENVERS : les questions\n"
            "  qu'il faut envoyer au RAG sont plus proches de leur canonique que celles\n"
            "  qu'on pourrait servir depuis le cache. C'est spectaculaire, et c'est en\n"
            "  partie CONSTRUIT : les cas RAG sont des éditions minimales (un mot ajouté,\n"
            "  donc cosinus élevé par construction) et les cas CACHE des reformulations\n"
            "  complètes (donc cosinus bas par construction). Le dataset est adversarial,\n"
            "  il n'est pas représentatif du trafic réel.\n"
            "\n  Ce qu'on peut légitimement en conclure : sur les deux modes d'échec qui\n"
            "  comptent, le cosinus ne porte pas l'information nécessaire à la décision\n"
            "  — l'inversion est une DÉMONSTRATION D'EXISTENCE, pas un taux.\n"
            "  Ce qu'on ne peut PAS en conclure : « le cache se trompe 100 % du temps »,\n"
            "  ni retourner le test (servir quand le cosinus est bas serait absurde)."
        )
    return {"max_rag": max(rag), "min_cache": min(cache), "marge": marge, "auc": aire}


def section_lexical(cas: list[dict]) -> dict:
    titre("[6] CONTREFACTUEL LEXICAL — ressusciter le sparse suffirait-il ?")

    docs = [tokeniser(p.read_text(encoding="utf-8")) for p in sorted(CORPUS_MD.glob("*.md"))]
    questions = [tokeniser(c["question_canonique"]) for c in cas] + [tokeniser(c["question_variante"]) for c in cas]
    idf = idf_du_corpus(docs + questions)
    avgdl = sum(len(d) for d in docs) / len(docs) if docs else 0.0

    print(f"\n  Corpus IDF : {len(docs)} documents métier + {len(questions)} questions")
    print(f"\n{'idf_delta':>10} {'Δbm25':>9} {'cos':>7}  {'attendu':<7} {'delta_lexical':<30} id")
    print(f"{'-' * 100}")

    for c in cas:
        delta = [t.lower() for t in c["delta_lexical"]]
        c["idf_delta"] = max((idf.get(t, 0.0) for t in delta), default=0.0)
        # Ce que le lexical « voit » du changement : l'écart de score BM25 des deux
        # formulations contre le document source.
        source = CORPUS_MD / c["doc_source"]
        doc = tokeniser(source.read_text(encoding="utf-8")) if source.exists() else []
        c["delta_bm25"] = bm25(tokeniser(c["question_variante"]), doc, idf, avgdl) - bm25(
            tokeniser(c["question_canonique"]), doc, idf, avgdl
        )
        print(
            f"{c['idf_delta']:>10.3f} {c['delta_bm25']:>9.3f} {c['cosinus']:>7.4f}  "
            f"{c['attendu']:<7} {', '.join(delta)[:30]:<30} {c['id']}"
        )

    doit_cacher = [c for c in cas if c["attendu"] == "CACHE"]
    doit_rag = [c for c in cas if c["attendu"] == "RAG"]
    auc_cos = auc([c["cosinus"] for c in doit_cacher], [c["cosinus"] for c in doit_rag])
    auc_idf = auc([-c["idf_delta"] for c in doit_cacher], [-c["idf_delta"] for c in doit_rag])

    # Combiné : pénaliser le cosinus par la rareté du token ajouté.
    def auc_combine(lam: float) -> float:
        return auc(
            [c["cosinus"] - lam * c["idf_delta"] for c in doit_cacher],
            [c["cosinus"] - lam * c["idf_delta"] for c in doit_rag],
        )

    lambdas = [round(0.02 * k, 2) for k in range(26)]
    meilleur_lam = max(lambdas, key=auc_combine)

    print(f"\n  AUC cosinus seul            : {auc_cos:.3f}")
    print(f"  AUC idf_delta seul          : {auc_idf:.3f}")
    print(f"  AUC cos − λ·idf_delta       : {auc_combine(meilleur_lam):.3f}  (λ = {meilleur_lam})")

    print(
        "\n  CONCLUSION À LIRE EN ENTIER : ressusciter le vecteur sparse est\n"
        "  nécessaire mais **pas suffisant**. Deux cas le démontrent, et ils sont\n"
        "  dans le dataset exprès :\n"
        "\n"
        "   • `logs-parefeu` (attendu CACHE) et `onboarding-droits-dba` (attendu RAG)\n"
        "     ont tous deux un token rare ajouté, donc un idf_delta élevé. Le signal\n"
        "     lexical les traite pareil ; la bonne réponse diffère. Inséparables.\n"
        "\n"
        "   • `nikon-mail-non-marque` a pour delta deux mots-outils (« ne … pas »),\n"
        "     d'idf quasi nul et de cosinus quasi 1 : invisible aux DEUX signaux.\n"
        "     C'est pourtant le cas le plus grave — la bonne réponse est l'exacte\n"
        "     opposée de celle du cache.\n"
        "\n"
        "  Autrement dit : (a) interdire CANONIQUE sur les questions de suivi et\n"
        "  (b) ressusciter le sparse ne couvrent pas la négation. Seul un signal\n"
        "  sémantique — un rerank question↔réponse cachée avant de servir — l'atteint."
    )
    return {
        "auc_cosinus": auc_cos,
        "auc_idf_delta": auc_idf,
        "auc_combine": auc_combine(meilleur_lam),
        "lambda": meilleur_lam,
        "par_cas": {c["id"]: {"idf_delta": c["idf_delta"], "delta_bm25": c["delta_bm25"]} for c in cas},
    }


def section_pool(cas: list[dict], vecteurs_canoniques: list[list[float]], seuil: float) -> dict:
    titre("[7] POOL — ce que l'éval par paires sous-estime")
    print(
        "\n  La production ne compare pas une question à un point. `question.py:73`\n"
        "  remonte 15 chunks et `trouver_reponse_reutilisable` prend le max par\n"
        "  reponse_id sur l'ENSEMBLE. Le score effectif est donc max_i cos(q, p_i)\n"
        "  sur tout le corpus canonique : une statistique d'extremum, supérieure à\n"
        "  n'importe quel cosinus par paire. Le taux du §2 est une BORNE INFÉRIEURE."
    )

    ids = [c["id"] for c in cas]
    # La mésattribution se juge sur le TEXTE canonique, pas sur l'id du cas.
    # Plusieurs cas partagent délibérément une même question canonique (la variante
    # RAG et la variante CACHE d'une même question) : leurs points canoniques sont
    # le même texte, donc le même vecteur. Comparer les id ferait passer cette
    # égalité voulue pour une erreur d'attribution, et le rapport crierait au loup
    # sur trois cas parfaitement sains. Ce qui compte est : le pool a-t-il désigné
    # une question DIFFÉRENTE de celle dont ce cas est la variante ?
    textes = [c["question_canonique"] for c in cas]
    print(f"\n{'cos paire':>10} {'cos pool':>9} {'Δ':>7}  {'attendu':<7} {'argmax du pool':<32} id")
    print(f"{'-' * 100}")

    mesattributions = []
    for c in cas:
        scores = [cosinus(c["vecteur_variante"], v) for v in vecteurs_canoniques]
        j = max(range(len(scores)), key=lambda k: scores[k])
        c["cos_pool"] = scores[j]
        c["argmax_pool"] = ids[j]
        egare = textes[j] != c["question_canonique"]
        if egare:
            mesattributions.append(c)
        print(
            f"{c['cosinus']:>10.4f} {c['cos_pool']:>9.4f} {c['cos_pool'] - c['cosinus']:>+7.4f}  "
            f"{c['attendu']:<7} {ids[j][:32]:<32} {c['id']}{'  ⚠ MÉSATTRIBUTION' if egare else ''}"
        )

    rag = [c for c in cas if c["attendu"] == "RAG"]
    over_paire = sum(1 for c in rag if c["cosinus"] >= seuil) / len(rag) if rag else 0.0
    over_pool = sum(1 for c in rag if c["cos_pool"] >= seuil) / len(rag) if rag else 0.0
    print(f"\n  over-hit (paire) : {over_paire:.1%}")
    print(f"  over-hit (pool)  : {over_pool:.1%}   ← le chiffre à retenir")

    if mesattributions:
        print(
            f"\n  ⚠ {len(mesattributions)} mésattribution(s) : la variante est plus proche du point\n"
            "  canonique d'une AUTRE question. Ce mode d'échec est invisible en vue par\n"
            "  paires, et l'utilisateur reçoit une réponse VALIDÉE à une question que\n"
            "  personne n'a posée : " + ", ".join(c["id"] for c in mesattributions)
        )

    print("\n  Courbe d'échelle — cos effectif moyen selon la taille du pool canonique :")
    print("  (pool = la canonique du cas + N−1 distracteurs ; sans la sienne, on")
    print("   mesurerait un pool qui ne peut pas répondre, pas l'effet d'échelle.)")
    echelle = {}
    for n in (1, 2, 4, 8):
        n = min(n, len(vecteurs_canoniques))
        taux, moyennes = [], []
        for c in cas:
            propre = vecteurs_canoniques[textes.index(c["question_canonique"])]
            autres = [v for k, v in enumerate(vecteurs_canoniques) if textes[k] != c["question_canonique"]]
            pool = [propre, *autres[: n - 1]]
            s = max(cosinus(c["vecteur_variante"], v) for v in pool)
            moyennes.append(s)
            if c["attendu"] == "RAG":
                taux.append(s >= seuil)
        val = sum(taux) / len(taux) if taux else 0.0
        moy = sum(moyennes) / len(moyennes)
        echelle[n] = {"over_hit": val, "cos_effectif_moyen": moy}
        print(f"    pool = {n:>2} : cos effectif moyen {moy:.4f}   over-hit {val:>6.1%}  {barre(val)}")

    croissance = echelle[max(echelle)]["cos_effectif_moyen"] - echelle[min(echelle)]["cos_effectif_moyen"]
    print(
        f"\n  Croissance observée du cos effectif de N=1 à N={max(echelle)} : {croissance:+.4f}.\n"
        "  À 8 canoniques l'effet est encore marginal — c'est attendu, et ce n'est pas\n"
        "  un démenti : `max` sur N tirages croît en O(log N) pour des queues légères,\n"
        "  donc l'échelle du dataset ne peut pas montrer la pente. Ce que ce §7 établit\n"
        "  n'est pas une valeur mais un SENS : le score effectif est monotone croissant\n"
        "  en la taille du corpus canonique, jamais décroissant. Un seuil calibré sur un\n"
        "  petit corpus ne peut donc que se dégrader — et `seuil_canonique=3` garantit\n"
        "  que ce corpus grossit à chaque validation. La calibration a une date de\n"
        "  péremption ; il faut la rejouer, pas la figer."
    )
    return {
        "over_hit_paire": over_paire,
        "over_hit_pool": over_pool,
        "mesattributions": [c["id"] for c in mesattributions],
        "echelle": echelle,
    }


# ══════════════════════════════════════════════════════════════════════════════
# Entrée
# ══════════════════════════════════════════════════════════════════════════════


def preflight() -> None:
    """Prouver que `cos(q_gen, q_spec)` est bien le proxy de ce que fait la prod.

    `embedding.py:12` accepte `is_query` et **ne l'utilise jamais** : requête et
    passage sont encodés à l'identique, donc comparer deux questions entre elles
    reproduit exactement le calcul de production. Ce script en dépend entièrement.

    Le jour où quelqu'un câblera les préfixes query/passage de BGE-M3 — ce pour
    quoi `is_query` existe — cette équivalence tombera, et tous les chiffres
    ci-dessous deviendront faux **sans rien changer d'apparent**. D'où cet assert :
    on veut un échec bruyant, pas un rapport silencieusement invalide.
    """
    a = embed_texts(["témoin"], is_query=True)[0]["dense"]
    b = embed_texts(["témoin"], is_query=False)[0]["dense"]
    assert a == b, (
        "is_query modifie désormais l'embedding : cos(question, question) n'est plus "
        "le proxy du calcul de production. Réviser ce script avant de lire ses chiffres."
    )


def main() -> int:
    parseur = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parseur.add_argument("--seuil", type=float, default=settings.seuil_cosinus)
    parseur.add_argument("--limit", type=int, default=None, help="n'évaluer que les N premiers cas")
    parseur.add_argument("--json", action="store_true", help="rapport JSON sur stdout")
    parseur.add_argument("--pool", dest="pool", action="store_true", default=True)
    parseur.add_argument("--no-pool", dest="pool", action="store_false")
    args = parseur.parse_args()

    cas = json.loads(DATASET.read_text(encoding="utf-8"))["cas"]
    if args.limit:
        cas = cas[: args.limit]

    if not args.json:
        titre("ÉVAL CACHE OVER-HIT — embeddings Albert réels")
        print(f"\n  modèle       : {settings.albert_embeddings_model_name}")
        print(f"  seuil évalué : {args.seuil}")
        print(f"  dataset      : {len(cas)} cas")

    preflight()

    # Un seul appel par texte : le texte indexé est `question_suivi` si présent,
    # sinon la question du ticket (cf. feedback.py:52-57) — d'où `texte_indexe`.
    textes_canoniques = [c.get("texte_indexe") or c["question_canonique"] for c in cas]
    textes_variantes = [c["question_variante"] for c in cas]
    vecteurs = embed_texts(textes_canoniques + textes_variantes)
    canoniques = [v["dense"] for v in vecteurs[: len(cas)]]
    variantes = [v["dense"] for v in vecteurs[len(cas) :]]

    for c, vc, vv in zip(cas, canoniques, variantes, strict=True):
        c["cosinus"] = cosinus(vc, vv)
        c["vecteur_variante"] = vv

    rapport: dict = {
        "modele": settings.albert_embeddings_model_name,
        "seuil": args.seuil,
        "n": len(cas),
        "cosinus": {c["id"]: c["cosinus"] for c in cas},
    }

    if not args.json:
        section_paires(cas, args.seuil)
    rapport["confusion"] = _peut_etre(section_confusion, args.json, cas, args.seuil)
    rapport["taxonomie"] = _peut_etre(section_taxonomie, args.json, cas, args.seuil)
    rapport["balayage"] = _peut_etre(section_balayage, args.json, cas)
    rapport["separabilite"] = _peut_etre(section_separabilite, args.json, cas)
    rapport["lexical"] = _peut_etre(section_lexical, args.json, cas)
    if args.pool:
        rapport["pool"] = _peut_etre(section_pool, args.json, cas, canoniques, args.seuil)

    if args.json:
        print(json.dumps(rapport, ensure_ascii=False, indent=2, default=float))
    else:
        titre("CE QUE CE RAPPORT PERMET DE TRANCHER")
        print(
            "\n  Trois correctifs candidats, à départager sur les chiffres ci-dessus :\n"
            "    (a) interdire la branche CANONIQUE quand `est_suivi` (question.py:101)\n"
            "    (b) ressusciter le vecteur sparse (embedding.py:31)\n"
            "    (c) passer un rerank question↔réponse cachée avant de servir\n"
            "\n  L'hypothèse à falsifier : (a) et (b) réunis NE SUFFISENT PAS, parce que\n"
            "  `nikon-mail-non-marque` échappe aux deux — cf. §6.\n"
            "\n  Et avant de citer un taux : 8 paires ⇒ ±35 points d'intervalle. Étendre\n"
            "  le dataset à ≥30 paires par polarité est le préalable à toute publication."
        )
    return 0


def _muet(fonction, *args):
    """Exécute une section en avalant son impression — pour le mode --json."""
    import contextlib
    import io

    with contextlib.redirect_stdout(io.StringIO()):
        return fonction(*args)


def _peut_etre(fonction, silencieux: bool, *args):
    return _muet(fonction, *args) if silencieux else fonction(*args)


if __name__ == "__main__":
    raise SystemExit(main())
