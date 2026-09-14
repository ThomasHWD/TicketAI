"""Test en condition réelle du cache sémantique, sur la fixture FAQ DFE.

La règle du projet est asymétrique : mieux vaut qu'une question repasse par le
RAG que d'être servie à tort. Un faux positif — réponse canonique servie sans
revue humaine à une question qui n'est pas la même — est une faute ; un faux
négatif n'est qu'un coût. Ce script mesure cette asymétrie de bout en bout.

`test_garde_reel.py` teste `approuver()` isolément. Ici on teste la **chaîne** :
recherche → seuil `SEUIL_COSINUS` → juge. Les trois maillons peuvent refuser,
et savoir lequel refuse est le résultat le plus utile du test.

Deux passes :

  A (défaut) — rejoue la décision de branche de `workers/question.py:65-110`
      sans rerank ni génération. Ce qui est sous test, c'est *si* le système
      bascule en RAG, pas le texte produit ensuite. N'écrit rien.
  B (--bout-en-bout) — un sous-ensemble poussé dans la vraie file Celery, pour
      vérifier que le rejeu de la passe A est fidèle (`Reponse.source` en base)
      et juger la qualité des réponses générées face à la référence FAQ.

    PYTHONPATH=. python scripts/test_cache_semantique.py
    PYTHONPATH=. python scripts/test_cache_semantique.py --bout-en-bout
    PYTHONPATH=. python scripts/test_cache_semantique.py --json resultats.json

⚠️  Prérequis : `scripts/seed_faq_dfe.py` doit avoir été exécuté.
⚠️  Consomme des appels Albert : 1 embedding par cas, 1 appel garde par cas
    franchissant le seuil (hors court-circuit typographique).
"""

import json
import os
import sys
import time
import uuid
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.models.reponse import Reponse
from app.models.ticket import Ticket
from app.services import garde_cache
from app.services.question_pipeline import (
    SEUIL_COSINUS,
    SEUIL_SUGGESTION,
    charger_contexte_fil,
    trouver_reponse_reutilisable,
)
from app.services.search import search_hybrid

DOMAINE = "DFE"
NS = uuid.UUID("dfe00000-1111-2222-3333-444444444444")
PAUSE = 1.0  # Albert ne renvoie pas de Retry-After sur 429 : on n'envoie pas en rafale


def sid(cle: str) -> uuid.UUID:
    return uuid.uuid5(NS, cle)


# ── Compteur d'appels au juge ──────────────────────────────────────────────────
# `approuver` court-circuite sans appel LLM quand les questions sont
# typographiquement identiques (garde_cache.py:37-39). Distinguer les deux est
# nécessaire : un « OUI » sans appel et un « OUI » du juge n'ont pas le même sens.
_appels_juge = 0
_chat_reel = garde_cache.chat


def _chat_compte(*args, **kwargs):
    global _appels_juge
    _appels_juge += 1
    return _chat_reel(*args, **kwargs)


garde_cache.chat = _chat_compte


# ── Cas de test ────────────────────────────────────────────────────────────────
# (famille, question, attendu, cible_attendue, commentaire)
#   attendu : CANONIQUE | SUGGESTION | RAG
#   cible_attendue : clé FAQ que le candidat *devrait* être, ou None si indifférent
#
# Rappel des entrées FAQ (cf. seed_faq_dfe.py) :
#   F1 engagement de dépense · F2 service fait · F3 monnaie étrangère
#   F4 certificat administratif (non canon) · F5 facture non réglée
#   F6 médecine de prévention · F7 dépense imprévue · F8 frais de déplacement
#   F9 mail justificatif (non canon) · F10 reliquat d'engagement
#   F11 collectivités territoriales (non canon)

CAS = [
    # ── A — Reformulations équivalentes → CANONIQUE ────────────────────────────
    ("A", "Quelle est la procédure pour saisir un engagement de dépense ?", "CANONIQUE", "F1",
     "reformulation de F1"),
    ("A", "Comment réaliser un engagement de dépense ?", "CANONIQUE", "F1",
     "verbe changé, même demande"),
    ("A", "Comment déclarer un service fait ?", "CANONIQUE", "F2",
     "faire = déclarer"),
    ("A", "Comment procède-t-on pour constater un service fait ?", "CANONIQUE", "F2",
     "tournure impersonnelle"),
    ("A", "Peut-on faire une demande d'engagement en devises étrangères ?", "CANONIQUE", "F3",
     "monnaie = devises"),
    ("A", "Est-il possible d'engager une dépense dans une autre monnaie que l'euro ?", "CANONIQUE", "F3",
     "reformulation par la négative implicite"),
    ("A", "Mon fournisseur me relance car sa facture n'a pas été payée, que faire ?", "CANONIQUE", "F5",
     "reformulation de F5"),
    ("A", "Faut-il un engagement de dépense pour la médecine de prévention ?", "CANONIQUE", "F6",
     "quasi identique à F6"),
    ("A", "J'ai une dépense que je n'avais pas prévue, comment procéder ?", "CANONIQUE", "F7",
     "reformulation de F7"),
    ("A", "Puis-je récupérer le reliquat d'un engagement que je n'utiliserai pas ?", "CANONIQUE", "F10",
     "reformulation de F10"),

    # ── B — Proches mais différentes → RAG (le cœur du test) ───────────────────
    # Grappe « Que dois-je faire ? » : F5 / F8 / F7, même tournure, services
    # destinataires différents. Une confusion ici envoie l'agent au mauvais service.
    # Attendu révisé le 05/09/2026 : « frais de mission » et « frais de
    # déplacements » désignent la même chose ici (F8 renvoie littéralement au
    # service « missions déplacements »). C'est une reformulation, pas une
    # nuance ; RAG était une prédiction du comportement d'alors, pas une exigence.
    ("B", "Mes frais de mission ne m'ont pas été remboursés, que dois-je faire ?", "CANONIQUE", "F8",
     "GRAPPE : doit viser F8, jamais F5"),
    ("B", "Mes frais de déplacement ne sont pas remboursés, dois-je contacter le service facturier ?",
     "RAG", "F8", "GRAPPE : question fermée, F8 nuance selon Siège/Région"),
    ("B", "Mon fournisseur n'a pas été payé, dois-je prévenir la mission Budget ?", "RAG", "F5",
     "GRAPPE : mélange F5 et F7"),
    ("B", "Ma facture est réglée mais le montant est faux, que dois-je faire ?", "RAG", None,
     "GRAPPE : hors FAQ, ne doit pas retomber sur F5"),
    # Grappe « Comment fait on X » : F1 / F2, jumelles lexicales
    ("B", "Comment fait-on un service fait partiel ?", "RAG", "F10",
     "GRAPPE : F10, jamais F2"),
    ("B", "Comment annule-t-on un engagement de dépense ?", "RAG", None,
     "GRAPPE : annuler ≠ créer, hors FAQ"),
    ("B", "Qui valide un engagement de dépense ?", "RAG", None,
     "GRAPPE : qui ≠ comment"),
    # Grappe général vs cas particulier
    ("B", "Faut-il un engagement de dépense pour une visite médicale ?", "RAG", "F6",
     "GRAPPE : F6 distingue cotisation et visite ; F1 tait l'exception"),
    ("B", "Faut-il un engagement de dépense pour une formation ?", "RAG", None,
     "GRAPPE : périmètre non couvert, ne doit pas servir F6 ni F1"),
    ("B", "Un devis en monnaie étrangère est-il recevable comme justificatif ?", "RAG", "F3",
     "GRAPPE : justificatif ≠ demande d'engagement"),
    ("B", "Un SMS suffit-il comme justificatif de demande d'engagement ?", "RAG", "F9",
     "GRAPPE : SMS ≠ mail, F9 conditionne au mail"),
    # Divers pièges de granularité et de négation
    ("B", "Combien de temps faut-il pour qu'un engagement soit validé ?", "RAG", None,
     "délai ≠ procédure"),
    ("B", "Que se passe-t-il si je ne fais pas de demande d'engagement ?", "RAG", None,
     "conséquence ≠ procédure"),
    ("B", "Comment connaître le montant de mon enveloppe budgétaire ?", "RAG", "F7",
     "F7 mentionne le BI/BR sans répondre à cela"),

    # ── C — Court-circuit typographique → CANONIQUE sans appel juge ────────────
    ("C", "comment fait on un engagement de dépense", "CANONIQUE", "F1",
     "COURT-CIRCUIT : casse et ponctuation retirées"),
    ("C", "COMMENT FAIT ON UN SERVICE FAIT ???", "CANONIQUE", "F2",
     "COURT-CIRCUIT : majuscules et ponctuation"),
    ("C", "Comment  fait  on   un  engagement   de  dépense ?", "CANONIQUE", "F1",
     "COURT-CIRCUIT : espaces multiples"),
    ("C", "Comment fait on un engagement de depense ?", "CANONIQUE", "F1",
     "ACCENTS : _normaliser ne les retire pas → doit passer par le juge"),

    # ── E — SUGGESTION : validées non canoniques, garde jamais appelé ──────────
    ("E", "Y a t il un modèle de certificat administratif ?", "SUGGESTION", "F4",
     "F4 validée non canonique"),
    ("E", "Existe-t-il un modèle de certificat administratif ?", "SUGGESTION", "F4",
     "reformulation, reste SUGGESTION"),
    ("E", "Comment connaitre les montants attribués par les collectivités territoriales ?",
     "SUGGESTION", "F11", "F11 validée non canonique"),

    # ── F — Hors périmètre → RAG, aucun candidat ──────────────────────────────
    ("F", "Comment poser mes congés payés ?", "RAG", None, "hors FAQ DFE"),
    ("F", "Comment réinitialiser mon mot de passe de session ?", "RAG", None,
     "hors FAQ ; vérifie aussi l'isolation avec le corpus IT"),
    ("F", "Combien de jours de télétravail par semaine ai-je le droit de faire ?", "RAG", None,
     "ISOLATION : question du corpus IT posée en domaine DFE, ne doit rien remonter"),
    ("F", "Quelle est la valeur des tickets restaurant ?", "RAG", None,
     "ISOLATION : canonique du domaine IT, invisible depuis DFE"),
    ("F", "Quel est le montant de la prime de fin d'année ?", "RAG", None, "hors FAQ"),
]

# ── Précisions (famille D) ─────────────────────────────────────────────────────
# (fil, précision, attendu, cible_attendue, commentaire)
# `search_hybrid` reçoit la précision **brute** (question.py:73) alors que le
# garde reçoit le fil **concaténé** (question.py:95). Cette asymétrie est
# exactement ce que ces cas mettent à l'épreuve.
PRECISIONS = [
    ("fil-engagement", "et pour la médecine de prévention ?", "RAG", "F6",
     "ASYMÉTRIE : précision elliptique, recherche sur 5 mots"),
    ("fil-engagement", "et si la dépense concerne la médecine de prévention ?", "RAG", "F6",
     "précision plus explicite, cible F6 et non F1"),
    ("fil-engagement", "et en monnaie étrangère ?", "RAG", "F3",
     "ASYMÉTRIE : elliptique, cible F3"),
    # Attendu révisé le 05/09/2026 : « la » se résout sans ambiguïté en « la
    # demande d'engagement » (seul antécédent du fil) et la question devient
    # mot pour mot F3. Servir F3 est la bonne décision.
    ("fil-engagement", "peut-on la faire en monnaie étrangère ?", "CANONIQUE", "F3",
     "précision explicite, cible F3"),
    ("fil-engagement", "comment fait on un engagement de dépense ?", "CANONIQUE", "F1",
     "précision qui répète la question initiale du fil"),
    ("fil-engagement", "et pour les congés payés ?", "RAG", None,
     "DÉRIVE : précision hors sujet dans le fil"),
    ("fil-facture", "et si ce sont mes frais de déplacement ?", "RAG", "F8",
     "GRAPPE + ASYMÉTRIE : ne doit surtout pas servir F5"),
    # Attendu révisé le 05/09/2026 : précision autonome, qui ne doit rien au
    # fil (« non plus » n'ajoute aucune condition) et redit F8. Le refus mesuré
    # avant le prompt suivi dédié venait de l'artefact de format, pas d'un doute.
    ("fil-facture", "mes frais de déplacement ne sont pas remboursés non plus, que faire ?",
     "CANONIQUE", "F8", "GRAPPE : explicite, cible F8"),
    ("fil-facture", "à quelle adresse dois-je écrire ?", "RAG", None,
     "ASYMÉTRIE : précision vide de sens hors du fil"),
    ("fil-servicefait", "et si la prestation n'a été que partiellement réalisée ?", "RAG", "F10",
     "GRAPPE : cible F10, jamais F2"),
    ("fil-servicefait", "comment récupérer le reliquat dans ce cas ?", "RAG", "F10",
     "cible F10"),
    # CAS LIMITE, le plus discutable des quatre attendus révisés le 05/09/2026.
    # « et pour X ? » après « comment fait-on Y ? » reporte le cadre interrogatif
    # sur X : la demande devient F1 mot pour mot, et F1 y répond. Une lecture
    # concurrente existe (« un service fait est-il requis pour un engagement ? »)
    # mais elle se dirait autrement. À surveiller : si une ellipse de cette forme
    # produit un jour un service hors cible, c'est ici qu'il faudra ajouter au
    # prompt suivi une clause « en cas de lecture multiple, réponds NON ».
    ("fil-servicefait", "et pour un engagement de dépense ?", "CANONIQUE", "F1",
     "ELLIPSE : bascule de sujet dans le fil, le garde voit le fil entier"),
]


def cle_de_reponse(db, reponse_id) -> str | None:
    """Retrouve la clé FAQ (F1…F11) d'une réponse de la fixture, pour le rapport."""
    for i in range(1, 30):
        if sid(f"r-F{i}") == reponse_id:
            return f"F{i}"
    return None


def evaluer(db, question: str, ticket_id=None) -> dict:
    """Rejoue la décision de branche de workers/question.py:65-110.

    S'arrête avant rerank et génération : la question posée est *si* le système
    bascule en RAG, pas le texte qu'il produirait ensuite.
    """
    global _appels_juge
    depart = _appels_juge

    est_suivi = ticket_id is not None
    requete_recherche = question
    if est_suivi:
        _, requete_recherche = charger_contexte_fil(ticket_id, question)

    chunks = search_hybrid(question, DOMAINE, top_k=15)  # question.py:73 — question brute
    top_score = chunks[0]["score_cosinus"] if chunks else 0.0
    candidat = trouver_reponse_reutilisable(db, chunks)
    reponse, score = candidat.reponse, candidat.score_cosinus
    question_du_point = candidat.question_indexee

    res = {
        "question": question,
        "est_suivi": est_suivi,
        "top_score": round(top_score, 4),
        "score_candidat": round(score, 4) if score is not None else None,
        # Second signal : la porte se franchit par le cosinus **ou** par lui.
        "score_lexical": round(candidat.score_lexical, 3) if candidat.score_lexical is not None else None,
        "candidat": cle_de_reponse(db, reponse.id) if reponse else None,
        "candidat_canonique": bool(reponse.canonique) if reponse else None,
        "question_indexee": None,
        "seuil_franchi": None,
        "verdict_garde": None,
        "appels_juge": 0,
    }

    if reponse is None:
        res["branche"] = "RAG"
        res["bloque_par"] = "AUCUN_CANDIDAT"
    elif reponse.canonique and candidat.franchit(SEUIL_COSINUS):  # question.py
        res["seuil_franchi"] = True
        # question.py:93 — la question du point retrouvé fait foi ; repli sur le
        # ticket d'origine pour les points antérieurs aux formulations multiples.
        question_indexee = question_du_point
        if not question_indexee:
            ticket_source = db.query(Ticket).filter(Ticket.id == reponse.ticket_id).first()
            question_indexee = reponse.question_suivi or (ticket_source.question if ticket_source else None)
        res["question_indexee"] = question_indexee
        a_comparer = requete_recherche if est_suivi else question  # question.py:95
        verdict = bool(
            question_indexee
            and garde_cache.approuver(a_comparer, question_indexee, est_suivi=est_suivi)
        )
        res["verdict_garde"] = verdict
        # Refus du garde → SUGGESTION (question.py), sauf si le candidat n'est
        # entré que par la porte lexicale : il repart alors au RAG.
        if verdict:
            res["branche"] = "CANONIQUE"
            res["bloque_par"] = None
        elif candidat.servable:
            res["branche"] = "SUGGESTION"
            res["bloque_par"] = "GARDE"
        else:
            res["branche"] = "RAG"
            res["bloque_par"] = "GARDE_LEXICAL_SEUL"
    elif reponse.canonique:
        res["seuil_franchi"] = False
        res["branche"] = "SUGGESTION" if candidat.servable else "RAG"
        res["bloque_par"] = "SEUIL" if candidat.servable else "LEXICAL_SEUL"
    else:
        res["branche"] = "SUGGESTION" if candidat.servable else "RAG"
        res["bloque_par"] = "NON_CANONIQUE" if candidat.servable else "LEXICAL_SEUL"

    res["appels_juge"] = _appels_juge - depart
    return res


def passe_a() -> list[dict]:
    db = SessionLocal()
    resultats = []
    try:
        total = len(CAS) + len(PRECISIONS)
        n = 0

        for famille, question, attendu, cible, commentaire in CAS:
            n += 1
            print(f"[{n:>2}/{total}] {famille} · {question[:66]}")
            r = evaluer(db, question)
            r.update(famille=famille, attendu=attendu, cible_attendue=cible, commentaire=commentaire)
            r["ok"] = r["branche"] == attendu
            resultats.append(r)
            print(f"          → {r['branche']:<10} (attendu {attendu}) "
                  f"candidat={r['candidat']} score={r['score_candidat']} juge={r['appels_juge']}")
            time.sleep(PAUSE)

        for cle_fil, precision, attendu, cible, commentaire in PRECISIONS:
            n += 1
            tid = sid(f"t-suivi-{cle_fil}")
            print(f"[{n:>2}/{total}] D · [{cle_fil}] {precision[:58]}")
            r = evaluer(db, precision, ticket_id=tid)
            r.update(famille="D", attendu=attendu, cible_attendue=cible, commentaire=commentaire, fil=cle_fil)
            r["ok"] = r["branche"] == attendu
            resultats.append(r)
            print(f"          → {r['branche']:<10} (attendu {attendu}) "
                  f"candidat={r['candidat']} score={r['score_candidat']} juge={r['appels_juge']}")
            time.sleep(PAUSE)
    finally:
        db.close()
    return resultats


def rapporter(resultats: list[dict]) -> None:
    print("\n" + "=" * 100)
    print("RÉCAPITULATIF")
    print("=" * 100)

    par_famille = {}
    for r in resultats:
        par_famille.setdefault(r["famille"], []).append(r)

    for famille in sorted(par_famille):
        lot = par_famille[famille]
        ok = sum(1 for r in lot if r["ok"])
        print(f"\n── Famille {famille} — {ok}/{len(lot)} conformes " + "─" * 50)
        for r in lot:
            marque = "✅" if r["ok"] else "❌"
            print(f"  {marque} {r['branche']:<10} att.{r['attendu']:<10} "
                  f"cand={str(r['candidat']):<5} score={str(r['score_candidat']):<7} "
                  f"bloc={str(r['bloque_par']):<14} {r['question'][:52]}")

    # ── Le résultat qui compte : les faux positifs ────────────────────────────
    # Critère de sûreté **objectif**, indépendant de la colonne `attendu` :
    # est un faux positif toute réponse servie sans revue humaine dont le
    # candidat n'est pas la réponse FAQ qui répond réellement à la question
    # (`cible_attendue`), y compris quand aucune ne convient (cible None).
    # `attendu` reste une prédiction de branche, révisable ; ce critère-ci ne
    # l'est pas — le relire à la lumière du comportement observé reviendrait à
    # blanchir une régression.
    faux_positifs = [
        r for r in resultats
        if r["branche"] == "CANONIQUE"
        and (r["cible_attendue"] is None or r["candidat"] != r["cible_attendue"])
    ]
    faux_negatifs = [r for r in resultats if r["attendu"] == "CANONIQUE" and r["branche"] != "CANONIQUE"]
    ecarts_branche = [r for r in resultats if r["branche"] == "CANONIQUE" and r["attendu"] != "CANONIQUE"]

    print("\n" + "=" * 100)
    print(f"FAUX POSITIFS (servi sans revue une réponse hors cible) : {len(faux_positifs)}"
          "  ← défauts bloquants")
    for r in faux_positifs:
        print(f"  ❌ posée   : {r['question']}")
        print(f"     indexée : {r['question_indexee']}")
        print(f"     servi {r['candidat']} au lieu de {r['cible_attendue']} "
              f"· score {r['score_candidat']} · {r['commentaire']}")

    print(f"\nCANONIQUE non prévus (sur la bonne cible) : {len(ecarts_branche)}"
          "  ← à réexaminer un par un, pas un défaut en soi")
    for r in ecarts_branche:
        print(f"  ? {r['question'][:70]} → {r['candidat']} @ {r['score_candidat']}")

    print(f"\nFAUX NÉGATIFS (RAG alors qu'équivalent) : {len(faux_negatifs)}  ← coût acceptable")
    for r in faux_negatifs:
        print(f"  ⚠️  {r['question'][:70]} (bloqué par {r['bloque_par']}, score {r['score_candidat']})")

    # ── Qui refuse : le seuil ou le juge ? ────────────────────────────────────
    refus = Counter(r["bloque_par"] for r in resultats if r["attendu"] == "RAG" and r["branche"] == "RAG")
    print("\nRÉPARTITION DES REFUS CORRECTS (famille B/D/F attendues en RAG) :")
    for cause, n in refus.most_common():
        print(f"  {str(cause):<16} {n}")

    print(f"\nAppels au juge réellement émis : {_appels_juge}")
    court_circuits = [r for r in resultats if r["seuil_franchi"] and r["appels_juge"] == 0]
    print(f"Court-circuits typographiques (0 appel LLM) : {len(court_circuits)}")
    for r in court_circuits:
        print(f"  ⚡ {r['question'][:80]}")

    total_ok = sum(1 for r in resultats if r["ok"])
    print(f"\nTOTAL : {total_ok}/{len(resultats)} conformes")


def passe_b() -> list[dict]:
    """Bout en bout : la vraie file Celery, pour vérifier que le rejeu est fidèle."""
    from app.workers.question import question_job

    sous_ensemble = [
        "Quelle est la procédure pour saisir un engagement de dépense ?",
        "Comment déclarer un service fait ?",
        "Mes frais de mission ne m'ont pas été remboursés, que dois-je faire ?",
        "Mon fournisseur n'a pas été payé, dois-je prévenir la mission Budget ?",
        "Comment fait-on un service fait partiel ?",
        "Faut-il un engagement de dépense pour une visite médicale ?",
        "Un SMS suffit-il comme justificatif de demande d'engagement ?",
        "Y a t il un modèle de certificat administratif ?",
        "comment fait on un engagement de dépense",
        "Comment poser mes congés payés ?",
        "Quelle est la valeur des tickets restaurant ?",
        "J'ai une dépense que je n'avais pas prévue, comment procéder ?",
    ]

    resultats = []
    db = SessionLocal()
    try:
        for i, question in enumerate(sous_ensemble, 1):
            print(f"[B {i:>2}/{len(sous_ensemble)}] {question[:70]}")
            job = question_job.delay(question, DOMAINE, None, None, "[TEST-CACHE] passe B")
            job.get(timeout=180)

            db.expire_all()
            ticket = (
                db.query(Ticket)
                .filter(Ticket.job_id == uuid.UUID(job.id))
                .first()
            )
            reponse = (
                db.query(Reponse).filter(Reponse.ticket_id == ticket.id).order_by(Reponse.created_at.desc()).first()
                if ticket
                else None
            )
            r = {
                "question": question,
                "ticket_id": str(ticket.id) if ticket else None,
                "source": reponse.source if reponse else None,
                "statut": reponse.statut if reponse else None,
                "score": reponse.score_similarite if reponse else None,
                "contenu": (reponse.contenu or "")[:1500] if reponse else None,
            }
            resultats.append(r)
            print(f"          → source={r['source']} statut={r['statut']} score={r['score']}")
            time.sleep(PAUSE)
    finally:
        db.close()
    return resultats


def main() -> None:
    print(f"Seuils effectifs : SEUIL_COSINUS={SEUIL_COSINUS} · SEUIL_SUGGESTION={SEUIL_SUGGESTION}")
    print(f"Domaine : {DOMAINE}\n")

    if "--bout-en-bout" in sys.argv:
        resultats = passe_b()
        print("\n" + "=" * 100)
        print("PASSE B — bout en bout")
        for r in resultats:
            print(f"  {str(r['source']):<12} {str(r['statut']):<12} {r['question'][:60]}")
    else:
        resultats = passe_a()
        rapporter(resultats)

    if "--json" in sys.argv:
        chemin = sys.argv[sys.argv.index("--json") + 1]
        with open(chemin, "w", encoding="utf-8") as f:
            json.dump(resultats, f, ensure_ascii=False, indent=2)
        print(f"\nRésultats écrits dans {chemin}")


if __name__ == "__main__":
    main()
