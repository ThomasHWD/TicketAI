"""Test en conditions réelles du juge de ré-vérification.

Appelle Albert directement via juger() — nécessite ALBERT_API_KEY dans .env.
Pas de base de données, pas de Qdrant.

Usage :
    PYTHONPATH=. python scripts/test_reverification_reel.py
    PYTHONPATH=. python scripts/test_reverification_reel.py --pause 8   # secondes entre appels

Catégories :
  CONTREDITE — le changement contredit directement la réponse (chiffre, délai, outil modifié)
  INTACTE    — le changement est dans une autre section ou ne modifie pas le fond
  INCERTAIN  — ambiguïté réelle (ajout d'exception, réorganisation) → relecture humaine attendue

Critères d'acceptation :
  CONTREDITE attendu : CONTREDITE = OK, INCERTAIN = tolérable, INTACTE = ERREUR CRITIQUE
  INTACTE attendu    : INTACTE = OK, INCERTAIN = tolérable, CONTREDITE = ERREUR
  INCERTAIN attendu  : INCERTAIN ou CONTREDITE = OK, INTACTE = ERREUR
"""

import argparse
import time

from app.services.diff import SENS_AJOUT, SENS_REECRITURE, Unite
from app.services.reverification_scoring import (
    VERDICT_CONTREDITE,
    VERDICT_INCERTAIN,
    VERDICT_INTACTE,
    juger,
)

CAS = [
    # ── CONTREDITE : chiffre, délai, taux ou outil changé ────────────────────
    {
        "cat": "CONTREDITE",
        "desc": "RH — télétravail 2j/sem → 3j/sem",
        "question": "Combien de jours de télétravail par semaine sont autorisés ?",
        "reponse": (
            "Le télétravail est autorisé jusqu'à 2 jours par semaine maximum, "
            "sur accord préalable du manager direct."
        ),
        "unites": [
            Unite(
                SENS_REECRITURE,
                "Le télétravail est limité à 2 jours par semaine, sur accord du manager.",
                "Le télétravail est limité à 3 jours par semaine, sur accord du manager.",
            )
        ],
        "attendu": VERDICT_CONTREDITE,
        "tolerables": [VERDICT_INCERTAIN],
    },
    {
        "cat": "CONTREDITE",
        "desc": "RH — congés annuels 25j → 28j",
        "question": "À combien de jours de congés payés ai-je droit chaque année ?",
        "reponse": (
            "Chaque salarié bénéficie de 25 jours ouvrés de congés payés par an, "
            "acquis à raison de 2,08 jours par mois travaillé."
        ),
        "unites": [
            Unite(
                SENS_REECRITURE,
                "Chaque salarié dispose de 25 jours ouvrés de congés payés annuels.",
                "Chaque salarié dispose de 28 jours ouvrés de congés payés annuels.",
            )
        ],
        "attendu": VERDICT_CONTREDITE,
        "tolerables": [VERDICT_INCERTAIN],
    },
    {
        "cat": "CONTREDITE",
        "desc": "IT — délai commande matériel 7j → 10j",
        "question": "Combien de jours à l'avance faut-il commander le matériel pour un nouvel arrivant ?",
        "reponse": (
            "La commande de matériel informatique doit être passée au moins 7 jours ouvrés "
            "avant la date d'arrivée du collaborateur."
        ),
        "unites": [
            Unite(
                SENS_REECRITURE,
                "La commande de matériel doit être passée au moins 7 jours ouvrés avant l'arrivée.",
                "La commande de matériel doit être passée au moins 10 jours ouvrés avant l'arrivée.",
            )
        ],
        "attendu": VERDICT_CONTREDITE,
        "tolerables": [VERDICT_INCERTAIN],
    },
    {
        "cat": "CONTREDITE",
        "desc": "RH — remboursement transport 50% → 75%",
        "question": "Quel est le taux de remboursement du Pass Navigo par l'employeur ?",
        "reponse": (
            "L'employeur rembourse 50 % du coût de l'abonnement de transport en commun "
            "(Pass Navigo ou équivalent)."
        ),
        "unites": [
            Unite(
                SENS_REECRITURE,
                "L'employeur prend en charge 50 % de l'abonnement de transport en commun.",
                "L'employeur prend en charge 75 % de l'abonnement de transport en commun.",
            )
        ],
        "attendu": VERDICT_CONTREDITE,
        "tolerables": [VERDICT_INCERTAIN],
    },
    {
        "cat": "CONTREDITE",
        "desc": "IT — VPN Cisco AnyConnect remplacé par Zscaler",
        "question": "Quel logiciel utiliser pour se connecter au réseau de l'entreprise en télétravail ?",
        "reponse": (
            "Pour accéder au réseau de l'entreprise depuis l'extérieur, il faut utiliser "
            "Cisco AnyConnect, disponible en téléchargement sur le portail IT."
        ),
        "unites": [
            Unite(
                SENS_REECRITURE,
                "L'accès distant au réseau se fait via Cisco AnyConnect, disponible sur le portail IT.",
                (
                    "L'accès distant au réseau se fait désormais via Zscaler Client Connector, "
                    "disponible sur le portail IT. Cisco AnyConnect n'est plus supporté depuis le 01/09/2026."
                ),
            )
        ],
        "attendu": VERDICT_CONTREDITE,
        "tolerables": [VERDICT_INCERTAIN],
    },
    {
        "cat": "CONTREDITE",
        "desc": "Legal — conservation contrats de travail 5 ans → 10 ans",
        "question": "Combien de temps doit-on conserver les contrats de travail ?",
        "reponse": (
            "Les contrats de travail doivent être conservés pendant une durée minimale "
            "de 5 ans après la fin du contrat."
        ),
        "unites": [
            Unite(
                SENS_REECRITURE,
                "Les contrats de travail doivent être archivés pendant au moins 5 ans après leur expiration.",
                (
                    "Les contrats de travail doivent être archivés pendant au moins 10 ans après leur "
                    "expiration, conformément à la mise à jour réglementaire 2025."
                ),
            )
        ],
        "attendu": VERDICT_CONTREDITE,
        "tolerables": [VERDICT_INCERTAIN],
    },

    # ── INTACTE : section différente, reformatage ou ajout neutre ────────────
    {
        "cat": "INTACTE",
        "desc": "RH — section formation modifiée, réponse sur les congés",
        "question": "Quelle est la durée maximale de congés consécutifs ?",
        "reponse": (
            "La durée maximale de congés consécutifs est de 24 jours ouvrables, "
            "sauf dérogation exceptionnelle validée par le manager."
        ),
        "unites": [
            Unite(
                SENS_REECRITURE,
                "Le budget formation est de 500 € par an et par salarié.",
                "Le budget formation est porté à 800 € par an et par salarié, renouvelable au 1er janvier.",
            )
        ],
        "attendu": VERDICT_INTACTE,
        "tolerables": [VERDICT_INCERTAIN],
    },
    {
        "cat": "INTACTE",
        "desc": "IT — reformatage liste logiciels (même contenu, présentation changée)",
        "question": "Quels logiciels de bureautique sont fournis sur le poste de travail ?",
        "reponse": "Les postes de travail sont équipés de Microsoft Word, Excel et Chrome pour la navigation web.",
        "unites": [
            Unite(
                SENS_REECRITURE,
                "Logiciels fournis : Word, Excel, Chrome.",
                "Suite bureautique fournie :\n- Microsoft Word\n- Microsoft Excel\n- Google Chrome (navigateur web)",
            )
        ],
        "attendu": VERDICT_INTACTE,
        "tolerables": [VERDICT_INCERTAIN],
    },
    {
        "cat": "INTACTE",
        "desc": "RH — ajout section télétravail étranger, délai demande inchangé",
        "question": "Quel est le délai pour soumettre une demande de télétravail ?",
        "reponse": (
            "La demande de télétravail doit être soumise au moins 5 jours ouvrés à l'avance "
            "via le portail RH."
        ),
        "unites": [
            Unite(
                SENS_AJOUT,
                None,
                (
                    "Télétravail à l'étranger : il est possible de télétravailler depuis l'étranger "
                    "pour une durée maximale de 15 jours consécutifs, sous réserve d'accord RH "
                    "et de validation fiscale préalable."
                ),
            )
        ],
        "attendu": VERDICT_INTACTE,
        "tolerables": [VERDICT_INCERTAIN],
    },
    {
        "cat": "INTACTE",
        "desc": "IT — numéro téléphone support changé (section adjacente), réponse sur procédure ticket",
        "question": "Comment signaler un incident informatique ?",
        "reponse": (
            "Pour signaler un incident, il faut ouvrir un ticket via le portail ITSM "
            "en renseignant la catégorie, la priorité et une description détaillée du problème."
        ),
        "unites": [
            Unite(
                SENS_REECRITURE,
                "Les incidents critiques peuvent aussi être signalés par téléphone au 01 23 45 67 89.",
                "Les incidents critiques peuvent aussi être signalés par téléphone au 01 98 76 54 32.",
            )
        ],
        "attendu": VERDICT_INTACTE,
        "tolerables": [VERDICT_INCERTAIN],
    },
    {
        "cat": "INTACTE",
        "desc": "Legal — reformulation du titre de section, fond identique",
        "question": "Quelles informations sont couvertes par la clause de confidentialité ?",
        "reponse": (
            "La clause de confidentialité couvre toutes les informations relatives aux clients, "
            "aux projets en cours et aux données financières non publiées."
        ),
        "unites": [
            Unite(
                SENS_REECRITURE,
                "3. Clause de confidentialité et protection des données sensibles",
                "3. Obligations de confidentialité et discrétion professionnelle",
            )
        ],
        "attendu": VERDICT_INTACTE,
        "tolerables": [VERDICT_INCERTAIN],
    },

    # ── INCERTAIN : ajout d'exception, réorganisation, nuance sans suppression ─
    {
        "cat": "INCERTAIN",
        "desc": "RH — liste pièces remboursement frais étendue (ajout sans retrait)",
        "question": "Quelles pièces fournir pour le remboursement des frais de déplacement professionnel ?",
        "reponse": (
            "Pour un remboursement de frais de déplacement, il faut fournir les justificatifs "
            "de transport (billets, tickets) et la note de frais complétée."
        ),
        "unites": [
            Unite(
                SENS_REECRITURE,
                "Pièces requises : justificatifs de transport, note de frais.",
                (
                    "Pièces requises : justificatifs de transport, note de frais, "
                    "attestation d'hébergement si nuit sur place, "
                    "et validation du manager N+1 pour les déplacements dépassant 300 €."
                ),
            )
        ],
        "attendu": VERDICT_INCERTAIN,
        "tolerables": [VERDICT_CONTREDITE],
    },
    {
        "cat": "INCERTAIN",
        "desc": "IT — procédure installation logiciel réorganisée en 4 étapes (vs 3)",
        "question": "Quelle est la procédure pour installer un logiciel non référencé sur son poste ?",
        "reponse": (
            "L'installation d'un logiciel non référencé requiert : une demande préalable au service IT, "
            "une validation du responsable sécurité, puis une installation supervisée par le support."
        ),
        "unites": [
            Unite(
                SENS_REECRITURE,
                "Procédure : 1) Demande au service IT, 2) Validation responsable sécurité, 3) Installation supervisée.",
                (
                    "Procédure : 1) Soumission d'une demande via le portail ITSM, "
                    "2) Analyse de sécurité par l'équipe SSI, "
                    "3) Décision d'approbation ou de refus, "
                    "4) Installation encadrée par le support si approuvée."
                ),
            )
        ],
        "attendu": VERDICT_INCERTAIN,
        "tolerables": [VERDICT_CONTREDITE],
    },
    {
        "cat": "INCERTAIN",
        "desc": "RH — préavis démission : exception cadres ancienneté > 10 ans ajoutée",
        "question": "Quelle est la durée du préavis en cas de démission ?",
        "reponse": (
            "En cas de démission, la durée du préavis est d'un mois pour les non-cadres "
            "et de trois mois pour les cadres."
        ),
        "unites": [
            Unite(
                SENS_REECRITURE,
                "Le préavis de démission est d'un mois pour les non-cadres et de trois mois pour les cadres.",
                (
                    "Le préavis de démission est d'un mois pour les non-cadres et de trois mois pour les cadres. "
                    "Exception : une convention collective sectorielle peut réduire ce délai "
                    "à 45 jours pour les cadres justifiant d'une ancienneté supérieure à 10 ans."
                ),
            )
        ],
        "attendu": VERDICT_INCERTAIN,
        "tolerables": [VERDICT_CONTREDITE],
    },
]


def main():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--pause", type=float, default=6.0,
                        help="Secondes entre chaque appel Albert (défaut : 6)")
    args = parser.parse_args()

    total = len(CAS)
    print(f"\nLancement de {total} appels Albert (pause {args.pause}s entre appels)…\n")

    resultats = []
    for i, cas in enumerate(CAS, 1):
        if i > 1:
            time.sleep(args.pause)
        print(f"[{i:02d}/{total}] {cas['cat']} — {cas['desc']}…", end=" ", flush=True)
        try:
            obtenu, justif = juger(cas["question"], cas["reponse"], cas["unites"])
            ok = obtenu == cas["attendu"] or obtenu in cas["tolerables"]
            parfait = obtenu == cas["attendu"]
            if parfait:
                statut = "✅"
            elif ok:
                statut = "〜"  # tolérable
            else:
                statut = "❌"
            print(f"{statut}  (attendu={cas['attendu']}, obtenu={obtenu})")
            if not ok:
                print(f"       Justification : {justif}")
        except Exception as exc:
            ok, parfait, obtenu = False, False, None
            print(f"💥  ERREUR : {exc}")
        resultats.append((cas["cat"], cas["desc"], cas["attendu"], obtenu, ok, parfait))

    # ── Récapitulatif ──────────────────────────────────────────────────────────
    print("\n" + "═" * 72)
    print("RÉCAPITULATIF")
    print("═" * 72)

    cats = {"CONTREDITE": [], "INTACTE": [], "INCERTAIN": []}
    for cat, desc, attendu, obtenu, ok, parfait in resultats:
        cats[cat].append((desc, attendu, obtenu, ok, parfait))

    labels = {
        "CONTREDITE": "Changements qui CONTREDISENT la réponse   → attendu CONTREDITE",
        "INTACTE":    "Changements SANS EFFET sur la réponse      → attendu INTACTE",
        "INCERTAIN":  "Changements AMBIGUS (exception, ajout…)    → attendu INCERTAIN",
    }

    total_ok = 0
    total_parfait = 0
    for cat, label in labels.items():
        cas_cat = cats[cat]
        n_ok = sum(1 for *_, ok, _ in cas_cat if ok)
        n_parfait = sum(1 for *_, _, parfait in cas_cat if parfait)
        total_ok += n_ok
        total_parfait += n_parfait
        print(f"\n{label}")
        print(f"  Résultat : {n_parfait}/{len(cas_cat)} parfaits, {n_ok}/{len(cas_cat)} acceptables")
        echecs = [(desc, att, obt) for desc, att, obt, ok, _ in cas_cat if not ok]
        for desc, att, obt in echecs:
            print(f"  ❌  {desc}  (attendu={att}, obtenu={obt})")

    print(f"\n{'═' * 72}")
    print(f"TOTAL : {total_parfait}/{total} parfaits · {total_ok}/{total} acceptables")
    if total_ok == total:
        print("✅ TOUT OK")
    elif total_ok >= total - 1:
        print("〜 QUASI-OK (1 tolérable raté)")
    else:
        print("❌ ÉCHECS À ANALYSER")
    print("═" * 72 + "\n")


if __name__ == "__main__":
    main()
