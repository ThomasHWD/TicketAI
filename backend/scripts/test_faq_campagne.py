"""Campagne de mesure de la page FAQ, sur la fixture DFE.

`test_cache_semantique.py` mesure ce que le système **sert** ; ici on mesure ce
qu'il **montre**. Les deux n'ont pas le même contrat : la FAQ est une
consultation en lecture seule, sans ticket, sans génération et **sans juge**.
C'est cette absence de juge qui fait tout l'intérêt de la mesure — ailleurs, un
candidat douteux est soumis à un arbitre ; ici, rien ne vient le confirmer.

Ce qui est vérifié se range en trois catégories, et elles n'ont pas le même poids.

**Invariants** (bloquants) — ils ne viennent pas d'un jugement de ma part mais de
`services/faq.py` et de CLAUDE.md :

  I1  aucune réponse non canonique ne paraît, dans aucun des deux rangs
      (F4/F9/F11 sont validées mais non canoniques : le filtre Postgres est la
      seule chose qui les retient) ;
  I2  `incertains` n'est rendu que si `resultats` est vide — règle métier :
      proposer de l'incertain à côté d'une réponse sûre ne fait que la diluer ;
  I3  tout élément de `resultats` a un cosinus ≥ `FAQ_SEUIL_PERTINENCE`. C'est la
      formulation observable de « un candidat entré par la seule porte lexicale
      va en piste, jamais en réponse » ;
  I4  une question hors périmètre ne produit aucun `resultats`. Hors périmètre
      veut dire **absente du corpus** (famille F), et non « d'un autre domaine » :
      la FAQ interroge tous domaines confondus, délibérément (famille T).

**Rappel** (mesuré, non bloquant) — une reformulation d'une entrée canonique
doit faire remonter cette entrée dans `resultats`. C'est l'utilité de la page.

**Confusions** (signalées, non bloquantes) — les interdictions de grappe reprises
de la vérité terrain du cache sémantique (« doit viser F8, jamais F5 »). Sur une
page de recherche, un voisin affiché n'est pas une faute au même titre qu'une
réponse servie : on le compte et on le lit, on n'en fait pas un échec.

Deux passes pour **un seul** embedding par question : l'appel Albert est mis en
cache, et la seconde passe rejoue la même recherche avec
`SEUIL_LEXICAL_PAR_TERME = 0`, c'est-à-dire la porte lexicale fermée. L'écart
entre les deux est la contribution nette de BM25 à la FAQ, mesurée et non
supposée.

Usage :
    PYTHONPATH=. python scripts/test_faq_campagne.py
    PYTHONPATH=. python scripts/test_faq_campagne.py --json resultats_faq.json

⚠️  Prérequis : `scripts/seed_faq_dfe.py` doit avoir été exécuté.
⚠️  Coût : 1 embedding Albert par cas (35), zéro appel LLM — la FAQ n'en fait pas.
"""

import argparse
import json
import os
import sys
import time
import uuid
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# La stack de développement n'écoute pas sur les ports du `.env` (qui décrit la
# prod). Sans ces valeurs, la campagne interroge une instance vide et rend un
# résultat parfaitement propre, parfaitement faux.
os.environ.setdefault("QDRANT_HOST", "localhost")
os.environ.setdefault("QDRANT_PORT", "6335")
os.environ.setdefault("POSTGRES_HOST", "localhost")
os.environ.setdefault("POSTGRES_PORT", "5433")

from app.config import settings  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.services import search  # noqa: E402
from app.services.faq import rechercher_faq  # noqa: E402

NS = uuid.UUID("dfe00000-1111-2222-3333-444444444444")
PAUSE = 1.0  # Albert ne renvoie pas de Retry-After sur 429 : on n'envoie pas en rafale

# Cf. seed_faq_dfe.py — F4/F9/F11 sont validées mais **non** canoniques.
NON_CANONIQUES = {"F4", "F9", "F11"}


def cle_de_reponse(reponse_id: str) -> str:
    """Clé FAQ (F1…F11) d'une réponse de la fixture, ou son id s'il est étranger."""
    for i in range(1, 30):
        if str(uuid.uuid5(NS, f"r-F{i}")) == reponse_id:
            return f"F{i}"
    return reponse_id[:8]


# ── Cas ────────────────────────────────────────────────────────────────────────
# (famille, question, attendus, interdits, commentaire)
#   attendus  : clés qui devraient figurer dans `resultats` (mesure de rappel)
#   interdits : clés qui ne devraient figurer dans aucun rang (confusion signalée)
#
# Les questions viennent telles quelles de `test_cache_semantique.py` : c'est la
# même vérité terrain, relue sous le contrat de la FAQ. Les familles D (suivi) et
# les cas de court-circuit typographique du garde n'ont pas d'équivalent ici —
# la FAQ ne connaît ni fil ni juge.
CAS = [
    # ── A — Reformulations d'entrées canoniques : la raison d'être de la page ──
    ("A", "Quelle est la procédure pour saisir un engagement de dépense ?", {"F1"}, set(),
     "reformulation de F1"),
    ("A", "Comment réaliser un engagement de dépense ?", {"F1"}, set(),
     "verbe changé, même demande"),
    ("A", "Comment déclarer un service fait ?", {"F2"}, set(),
     "faire = déclarer"),
    ("A", "Comment procède-t-on pour constater un service fait ?", {"F2"}, set(),
     "tournure impersonnelle"),
    ("A", "Peut-on faire une demande d'engagement en devises étrangères ?", {"F3"}, set(),
     "monnaie = devises"),
    ("A", "Est-il possible d'engager une dépense dans une autre monnaie que l'euro ?", {"F3"}, set(),
     "reformulation par la négative implicite"),
    ("A", "Mon fournisseur me relance car sa facture n'a pas été payée, que faire ?", {"F5"}, set(),
     "reformulation de F5"),
    ("A", "Faut-il un engagement de dépense pour la médecine de prévention ?", {"F6"}, set(),
     "quasi identique à F6"),
    ("A", "J'ai une dépense que je n'avais pas prévue, comment procéder ?", {"F7"}, set(),
     "reformulation de F7"),
    ("A", "Puis-je récupérer le reliquat d'un engagement que je n'utiliserai pas ?", {"F10"}, set(),
     "reformulation de F10"),

    # ── C — Variantes typographiques : mêmes mots, casse et ponctuation autres ──
    # Le court-circuit du garde n'existe pas dans la FAQ : ces questions doivent
    # remonter par le cosinus seul, ce qui en fait un plancher de la recherche.
    ("C", "comment fait on un engagement de dépense", {"F1"}, set(), "casse et ponctuation retirées"),
    ("C", "COMMENT FAIT ON UN SERVICE FAIT ???", {"F2"}, set(), "majuscules et ponctuation"),
    ("C", "Comment fait on un engagement de depense ?", {"F1"}, set(), "accents retirés"),

    # ── B — Voisines : ce que la page a le droit de montrer, et ce qu'elle ne doit pas ──
    ("B", "Mes frais de mission ne m'ont pas été remboursés, que dois-je faire ?", {"F8"}, {"F5"},
     "GRAPPE : doit viser F8, jamais F5"),
    ("B", "Mes frais de déplacement ne sont pas remboursés, dois-je contacter le service facturier ?",
     {"F8"}, {"F5"}, "GRAPPE : F8 nuance selon Siège/Région"),
    ("B", "Mon fournisseur n'a pas été payé, dois-je prévenir la mission Budget ?", {"F5"}, set(),
     "GRAPPE : mélange F5 et F7"),
    ("B", "Ma facture est réglée mais le montant est faux, que dois-je faire ?", set(), {"F5"},
     "GRAPPE : hors FAQ, ne doit pas retomber sur F5"),
    ("B", "Comment fait-on un service fait partiel ?", {"F10"}, set(),
     "GRAPPE : cible F10, F2 reste un voisin acceptable en page de recherche"),
    ("B", "Comment annule-t-on un engagement de dépense ?", set(), set(),
     "annuler ≠ créer, hors FAQ"),
    ("B", "Qui valide un engagement de dépense ?", set(), set(), "qui ≠ comment"),
    ("B", "Faut-il un engagement de dépense pour une visite médicale ?", {"F6"}, set(),
     "F6 distingue cotisation et visite"),
    ("B", "Un devis en monnaie étrangère est-il recevable comme justificatif ?", set(), set(),
     "justificatif ≠ demande d'engagement"),
    ("B", "Combien de temps faut-il pour qu'un engagement soit validé ?", set(), set(),
     "délai ≠ procédure"),
    ("B", "Que se passe-t-il si je ne fais pas de demande d'engagement ?", set(), set(),
     "conséquence ≠ procédure"),

    # ── E — Entrées validées NON canoniques : le filtre Postgres, seul rempart ──
    # Ces questions sont quasi mot pour mot celles de la fixture : le cosinus sera
    # au plafond. Rien ne doit paraître, dans aucun rang. C'est l'invariant I1, et
    # le seul endroit où la campagne le met réellement sous tension.
    ("E", "Y a t il un modèle de certificat administratif ?", set(), {"F4"},
     "F4 validée non canonique"),
    ("E", "Existe-t-il un modèle de certificat administratif ?", set(), {"F4"},
     "reformulation de F4"),
    ("E", "Comment connaitre les montants attribués par les collectivités territoriales ?", set(), {"F11"},
     "F11 validée non canonique"),
    ("E", "Un mail suffit-il comme justificatif de demande d'engagement ?", set(), {"F9"},
     "F9 validée non canonique"),

    # ── F — Hors périmètre : `resultats` doit rester vide (invariant I4) ───────
    ("F", "Comment poser mes congés payés ?", set(), set(), "hors FAQ DFE"),
    ("F", "Comment réinitialiser mon mot de passe de session ?", set(), set(), "hors FAQ"),
    ("F", "Quel est le montant de la prime de fin d'année ?", set(), set(), "hors FAQ"),
    ("F", "Quelle est la capitale de la Mongolie ?", set(), set(),
     "absurde : le repli ne doit pas devenir un fourre-tout"),
    # ── T — Hors DFE mais **dans** le corpus : la FAQ n'est pas cloisonnée ─────
    # Famille distincte de F, et la distinction est de fond. Dans le pipeline ces
    # questions sont des cas d'isolation : posées en domaine DFE, elles ne doivent
    # rien remonter. Dans la FAQ, `rechercher_points_reponses` interroge **tous
    # domaines confondus** — un utilisateur lambda n'appartient à aucun groupe, et
    # ce qui est exposé a été validé au moins `SEUIL_CANONIQUE` fois pour être
    # servi tel quel. Servir ici la canonique du corpus général est donc le
    # comportement correct, et l'invariant I4 ne s'y applique pas.
    ("T", "Combien de jours de télétravail par semaine ai-je le droit de faire ?", set(), set(),
     "TOUS DOMAINES : doit pouvoir remonter la canonique hors DFE"),
    ("T", "Quelle est la valeur des tickets restaurant ?", set(), set(),
     "TOUS DOMAINES : doit pouvoir remonter la canonique hors DFE"),
]


# ── Cache d'embedding ──────────────────────────────────────────────────────────
# Les deux passes posent exactement les mêmes questions. Sans ce cache, la
# seconde rachèterait 35 requêtes Albert pour recalculer un vecteur identique.
_embed_reel = search.embed_texts
_cache: dict[tuple, list] = {}
_appels_albert = 0


def _embed_cache(textes, is_query=False):
    global _appels_albert
    cle = (tuple(textes), is_query)
    if cle not in _cache:
        _appels_albert += 1
        _cache[cle] = _embed_reel(textes, is_query=is_query)
        time.sleep(PAUSE)
    return _cache[cle]


search.embed_texts = _embed_cache


# ── Capture des scores ─────────────────────────────────────────────────────────
# Les scores **ne sortent pas de l'API** — c'est une décision de conception, pas
# un oubli. Mais l'invariant I3 porte précisément sur le cosinus d'un résultat
# servi : on intercepte donc les chunks en amont, là où ils existent encore.
_chunks_captures: list[dict] = []
_recherche_reelle = None


def _capturer(question: str, top_k: int) -> list[dict]:
    chunks = _recherche_reelle(question, top_k)
    _chunks_captures.clear()
    _chunks_captures.extend(chunks)
    return chunks


def _cosinus_par_reponse() -> dict[str, float]:
    """Meilleur cosinus observé par `reponse_id`, pour relire I3."""
    meilleurs: dict[str, float] = {}
    for chunk in _chunks_captures:
        rid = chunk.get("reponse_id")
        if rid:
            cle = str(rid)
            meilleurs[cle] = max(meilleurs.get(cle, 0.0), chunk.get("score_cosinus", 0.0))
    return meilleurs


def evaluer(db, question: str) -> dict:
    sortie = rechercher_faq(db, question, limite=settings.faq_max_resultats)
    cosinus = _cosinus_par_reponse()
    return {
        "resultats": [
            {"cle": cle_de_reponse(r["reponse_id"]), "cosinus": round(cosinus.get(r["reponse_id"], 0.0), 4)}
            for r in sortie["resultats"]
        ],
        "incertains": [
            {"cle": cle_de_reponse(r["reponse_id"]), "cosinus": round(cosinus.get(r["reponse_id"], 0.0), 4)}
            for r in sortie["incertains"]
        ],
    }


def controler(famille: str, attendus: set, interdits: set, obtenu: dict) -> dict:
    """Invariants bloquants d'abord, rappel et confusions ensuite."""
    resultats = [r["cle"] for r in obtenu["resultats"]]
    incertains = [r["cle"] for r in obtenu["incertains"]]
    vus = set(resultats) | set(incertains)

    violations = []
    fuite = vus & NON_CANONIQUES
    if fuite:
        violations.append(f"I1 non canonique exposée : {', '.join(sorted(fuite))}")
    if resultats and incertains:
        violations.append("I2 pistes rendues alors que des réponses existent")
    sous_seuil = [r for r in obtenu["resultats"] if r["cosinus"] < settings.faq_seuil_pertinence]
    if sous_seuil:
        détail = ", ".join(f"{r['cle']}@{r['cosinus']}" for r in sous_seuil)
        violations.append(f"I3 servi sous le seuil de pertinence : {détail}")
    if famille == "F" and resultats:
        violations.append(f"I4 hors périmètre servi : {', '.join(resultats)}")

    return {
        "violations": violations,
        "rappel_ok": attendus <= set(resultats) if attendus else None,
        "manquants": sorted(attendus - set(resultats)),
        "confusions": sorted(interdits & vus),
    }


def rendre(cas: list, titre: str) -> dict:
    print(f"\n{'=' * 96}\n{titre}\n{'=' * 96}")
    compteur = Counter()
    lignes = []
    db = SessionLocal()
    try:
        for famille, question, attendus, interdits, commentaire in cas:
            obtenu = evaluer(db, question)
            bilan = controler(famille, attendus, interdits, obtenu)

            compteur["cas"] += 1
            compteur["violations"] += len(bilan["violations"])
            if bilan["rappel_ok"] is True:
                compteur["rappel_ok"] += 1
            elif bilan["rappel_ok"] is False:
                compteur["rappel_manque"] += 1
            compteur["confusions"] += len(bilan["confusions"])
            compteur["resultats_vides"] += 0 if obtenu["resultats"] else 1
            compteur["pistes_seules"] += 1 if (not obtenu["resultats"] and obtenu["incertains"]) else 0

            marque = "✗" if bilan["violations"] else ("○" if bilan["rappel_ok"] is False else "✓")
            rendu = ", ".join(f"{r['cle']}({r['cosinus']})" for r in obtenu["resultats"]) or "—"
            pistes = ", ".join(f"{r['cle']}({r['cosinus']})" for r in obtenu["incertains"])
            print(f"{marque} [{famille}] {question[:66]:<66} → {rendu}")
            if pistes:
                print(f"      pistes : {pistes}")
            for v in bilan["violations"]:
                print(f"      ⚠ {v}")
            if bilan["manquants"]:
                print(f"      rappel manqué : {', '.join(bilan['manquants'])} — {commentaire}")
            if bilan["confusions"]:
                print(f"      confusion : {', '.join(bilan['confusions'])} — {commentaire}")

            lignes.append(
                {
                    "famille": famille,
                    "question": question,
                    "attendus": sorted(attendus),
                    "obtenu": obtenu,
                    **bilan,
                }
            )
    finally:
        db.close()

    print(f"\n  cas                     {compteur['cas']}")
    print(f"  violations d'invariant  {compteur['violations']}   ← seul chiffre bloquant")
    print(f"  rappel satisfait        {compteur['rappel_ok']}/{compteur['rappel_ok'] + compteur['rappel_manque']}")
    print(f"  confusions de grappe    {compteur['confusions']}")
    print(f"  sans aucun résultat     {compteur['resultats_vides']}  (dont {compteur['pistes_seules']} avec pistes)")
    return {"titre": titre, "compteur": dict(compteur), "cas": lignes}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", help="écrit le détail dans ce fichier")
    args = parser.parse_args()

    global _recherche_reelle
    import app.services.faq as module_faq

    _recherche_reelle = module_faq.rechercher_points_reponses
    module_faq.rechercher_points_reponses = _capturer

    print(f"seuils FAQ : pertinence={settings.faq_seuil_pertinence} incertain={settings.faq_seuil_incertain}")
    print(f"porte lexicale : SEUIL_LEXICAL_PAR_TERME={settings.seuil_lexical_par_terme}")

    avec = rendre(CAS, "PASSE 1 — configuration courante (porte lexicale ouverte)")

    # Passe 2 : la porte lexicale refermée, c'est-à-dire le comportement d'avant
    # BM25. Aucun appel Albert supplémentaire — les embeddings sont en cache.
    ancien = settings.seuil_lexical_par_terme
    settings.seuil_lexical_par_terme = 0.0
    try:
        sans = rendre(CAS, "PASSE 2 — porte lexicale fermée (SEUIL_LEXICAL_PAR_TERME=0)")
    finally:
        settings.seuil_lexical_par_terme = ancien

    print(f"\n{'=' * 96}\nÉCART ENTRE LES DEUX PASSES — contribution nette de BM25 à la FAQ\n{'=' * 96}")
    ecarts = 0
    for a, s in zip(avec["cas"], sans["cas"], strict=True):
        if a["obtenu"] != s["obtenu"]:
            ecarts += 1
            print(f"  [{a['famille']}] {a['question'][:70]}")
            print(f"      porte ouverte : {a['obtenu']}")
            print(f"      porte fermée  : {s['obtenu']}")
    if not ecarts:
        print("  aucun — la porte lexicale ne change rien sur ce jeu de questions.")

    print(f"\nappels Albert (embeddings) : {_appels_albert}")

    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump({"avec_porte": avec, "sans_porte": sans}, f, ensure_ascii=False, indent=2)
        print(f"détail écrit dans {args.json}")

    return 1 if avec["compteur"].get("violations") else 0


if __name__ == "__main__":
    raise SystemExit(main())
