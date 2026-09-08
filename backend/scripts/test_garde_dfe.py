"""Test en conditions réelles du garde du cache canonique — domaine DFE/Finances.

Questions et réponses issues de la FAQ du Département des Finances et de l'Évaluation
(ONaCVG) : engagements de dépense, service fait, certificat administratif, factures
impayées, médecine de prévention, frais de déplacement, budget.

Appelle Albert directement via approuver() — nécessite ALBERT_API_KEY dans .env.
Pas de base de données, pas de Qdrant.

Usage :
    PYTHONPATH=. python scripts/test_garde_dfe.py
"""

from app.services.garde_cache import approuver

# ── Format des cas ─────────────────────────────────────────────────────────────
# (categorie, question_posee, question_indexee, attendu_bool, description)

CAS = [
    # ── Catégorie A : proches mais DIFFÉRENTES → doit aller en RAG (attendu=False) ──
    ("A-NON",
     "Comment faire un engagement de dépense ?",
     "Comment faire un service fait ?",
     False,
     "engagement ≠ service fait, deux procédures distinctes"),

    ("A-NON",
     "Faut-il un engagement préalable pour une visite médicale de prévention ?",
     "Faut-il un engagement préalable pour la cotisation annuelle de médecine de prévention ?",
     False,
     "visite (aucun engagement) ≠ cotisation annuelle (engagement obligatoire)"),

    ("A-NON",
     "Ma facture n'est pas réglée, je suis agent au Siège. Que faire ?",
     "Ma facture n'est pas réglée, je suis en service départemental. Que faire ?",
     False,
     "Siège (via missions-déplacements) ≠ service départemental (sfact direct)"),

    ("A-NON",
     "Puis-je récupérer un reliquat d'engagement sur un exercice de l'année précédente ?",
     "Puis-je récupérer le reliquat d'un engagement sur l'exercice en cours ?",
     False,
     "année précédente (impossible) ≠ année courante (possible via service fait partiel)"),

    ("A-NON",
     "Comment annuler totalement un engagement dont je n'ai plus besoin ?",
     "Comment récupérer le reliquat d'un engagement partiellement utilisé ?",
     False,
     "annulation complète ≠ restitution partielle via service fait partiel"),

    ("A-NON",
     "Un mail fournisseur suffit-il comme justificatif pour un engagement d'abonnement numérique ?",
     "Un devis suffit-il comme justificatif pour un engagement de prestation ?",
     False,
     "mail = conditions spécifiques requises (4 critères) ≠ devis = justificatif standard"),

    ("A-NON",
     "Mon engagement de dépense n'a pas été traité par la mission Engagements. Que faire ?",
     "Ma facture n'est pas réglée et mon fournisseur me relance. Que faire ?",
     False,
     "engagement bloqué (mission Engagements) ≠ facture impayée (service facturier)"),

    ("A-NON",
     "J'ai une dépense imprévue qui tient dans mon enveloppe budgétaire actuelle.",
     "J'ai une dépense imprévue qui dépasse mon enveloppe budgétaire.",
     False,
     "dans le budget (vérifier soutenabilité seul) ≠ hors budget (contacter mission Budget)"),

    ("A-NON",
     "Puis-je envoyer un bon de commande à un fournisseur sans numéro d'engagement ?",
     "Puis-je commander auprès d'un fournisseur sans mise en concurrence préalable ?",
     False,
     "absence de numéro d'engagement ≠ absence de mise en concurrence, deux obligations distinctes"),

    ("A-NON",
     "Comment connaître les montants des subventions des collectivités territoriales pour mon service ?",
     "Comment obtenir le bilan budgétaire complet de mon service ?",
     False,
     "subventions CT (mission Budget, montants titrés/rapprochés) ≠ bilan budgétaire global"),

    # ── Catégorie B : équivalentes → doit être servi CANONIQUE (attendu=True) ────
    ("B-OUI",
     "Comment saisir une demande d'engagement de dépense ?",
     "Comment fait-on un engagement de dépense ?",
     True,
     "saisir = faire, même procédure via formulaire intranet"),

    ("B-OUI",
     "Est-il possible d'établir une demande d'engagement en devises étrangères ?",
     "Peut-on faire une demande d'engagement en monnaie étrangère ?",
     True,
     "devises étrangères = monnaie étrangère, même réponse (non)"),

    ("B-OUI",
     "Où trouver le formulaire de certificat administratif sur l'intranet ?",
     "Y a-t-il un modèle de certificat administratif ?",
     True,
     "formulaire = modèle, même ressource sur l'intranet"),

    ("B-OUI",
     "Mon fournisseur me réclame le règlement d'une facture restée impayée.",
     "Ma facture n'est pas réglée et mon fournisseur me relance.",
     True,
     "réclamer règlement = relancer pour facture impayée, même situation"),

    ("B-OUI",
     "Comment déclarer la réception conforme d'une livraison fournisseur ?",
     "Comment fait-on un service fait ?",
     True,
     "déclarer réception conforme = constater le service fait"),

    ("B-OUI",
     "Un email indiquant la durée et le montant d'un abonnement est-il valable comme justificatif ?",
     "Un mail est-il suffisant pour établir une demande d'engagement pour un abonnement numérique ?",
     True,
     "email = mail, abonnement = abonnement numérique, même question"),

    ("B-OUI",
     "Comment rendre des crédits non consommés sur un engagement dont la prestation a coûté moins cher ?",
     "Peut-on récupérer le reliquat d'engagement si la prestation n'a pas été effectuée intégralement ?",
     True,
     "rendre crédits = récupérer reliquat = service fait partiel + mention restitution"),

    ("B-OUI",
     "Mes frais de mission ne m'ont pas été remboursés. Quelle démarche suivre ?",
     "Mes frais de déplacements ne sont pas remboursés. Que dois-je faire ?",
     True,
     "frais de mission = frais de déplacements, même procédure"),

    ("B-OUI",
     "Qui dois-je contacter pour obtenir les montants versés par les collectivités locales à mon service ?",
     "Comment puis-je connaître les montants attribués par les collectivités territoriales ?",
     True,
     "collectivités locales = collectivités territoriales, même interlocuteur : mission Budget"),

    ("B-OUI",
     "La médecine du travail nécessite-t-elle systématiquement un engagement préalable ?",
     "Faut-il faire un engagement de dépense pour la médecine de prévention ?",
     True,
     "médecine du travail = médecine de prévention, même règle bipartite"),

    # ── Catégorie C : précisions PROCHES (fil = Q initiale + précision) → OUI ───
    # question_posee = fil complet, question_indexee = réponse indexée correspondante
    ("C-OUI",
     "Comment faire un engagement de dépense ?\n"
     "Et si c'est pour une action Mémoire, y a-t-il des règles particulières ?",
     "Quelles sont les particularités d'un engagement de dépense pour une action Mémoire ?",
     True,
     "suivi : précision sur le contexte Mémoire (opération programmée, notifiée par le département Mémoire)"),

    ("C-OUI",
     "Ma facture n'est pas réglée.\nQuels éléments dois-je préciser dans mon mail au service facturier ?",
     "Que doit contenir le mail au service facturier pour signaler une facture impayée ?",
     True,
     "suivi : contenu du mail (numéro de tiers, nom fournisseur, numéro facture, montant, certificat Chorus)"),

    ("C-OUI",
     "Peut-on s'engager en monnaie étrangère ?\n"
     "Et si les documents justificatifs comme le devis sont libellés en dollars ?",
     "Les documents justificatifs d'une demande d'engagement peuvent-ils être en devise étrangère ?",
     True,
     "suivi : justificatifs en devise (devis, proposition commerciale) — même règle euros obligatoire"),

    ("C-OUI",
     "Comment récupérer un reliquat d'engagement ?\n"
     "Et si l'engagement a été réparti sur plusieurs comptes budgétaires ?",
     "Comment restituer un reliquat d'engagement réparti sur plusieurs comptes ?",
     True,
     "suivi : multi-comptes (préciser sur quel compte restituer)"),

    ("C-OUI",
     "Faut-il un engagement pour la médecine de prévention ?\nEt uniquement pour la cotisation annuelle ?",
     "Faut-il un engagement de dépense pour la cotisation annuelle de médecine de prévention ?",
     True,
     "suivi : restriction à la cotisation (oui, selon procédure habituelle)"),

    ("C-OUI",
     "J'ai une dépense imprévue.\nDois-je d'abord vérifier que mon enveloppe budgétaire peut absorber cette dépense ?",
     "Quelle est la première étape à faire face à une dépense imprévue ?",
     True,
     "suivi : vérification de la soutenabilité budgétaire avant toute autre démarche"),

    ("C-OUI",
     "Mes frais de déplacement ne sont pas remboursés.\nQuelle est l'adresse e-mail exacte du service facturier ?",
     "Quelle adresse e-mail contacter pour des frais de déplacement non remboursés en Région ?",
     True,
     "suivi : coordonnées du service facturier (sfact@onacvg.fr)"),

    ("C-OUI",
     "Comment faire un service fait ?\nQui a en charge cette constatation dans les services prescripteurs ?",
     "Qui est responsable de constater le service fait dans les services prescripteurs ?",
     True,
     "suivi : responsabilité des prescripteurs pour tout achat de bien ou service"),

    ("C-OUI",
     "Ma facture n'est pas réglée.\n"
     "Dois-je d'abord récupérer le certificat de dépôt Chorus Pro avant d'écrire au facturier ?",
     "Quelle est la première démarche pour signaler une facture impayée au service facturier ?",
     True,
     "suivi : séquençage (Chorus Pro d'abord, puis mail sfact)"),

    ("C-OUI",
     "Comment faire un engagement de dépense ?\n"
     "Le numéro d'engagement doit-il obligatoirement figurer sur le bon de commande ?",
     "Le bon de commande envoyé au fournisseur doit-il mentionner un numéro d'engagement ?",
     True,
     "suivi : mention obligatoire du numéro d'engagement sur le bon de commande"),

    # ── Catégorie D : précisions ÉLOIGNÉES (fil) → doit aller en RAG (attendu=False) ──
    ("D-NON",
     "Comment faire un engagement de dépense ?\nEt si le fournisseur refuse d'accepter notre bon de commande ?",
     "Quelle est la procédure pour faire un engagement de dépense ?",
     False,
     "suivi : refus du bon de commande = litige fournisseur, hors périmètre de la procédure d'engagement"),

    ("D-NON",
     "Ma facture n'est pas réglée.\nQue faire si le service facturier ne répond pas à mon mail après deux semaines ?",
     "Que faire si ma facture n'est pas réglée et mon fournisseur me relance ?",
     False,
     "suivi : silence du service facturier = escalade, procédure distincte de la démarche initiale"),

    ("D-NON",
     "Mes frais de déplacement ne sont pas remboursés.\nEt si j'ai égaré les originaux de mes justificatifs ?",
     "Mes frais de déplacements ne sont pas remboursés. Que dois-je faire ?",
     False,
     "suivi : justificatifs perdus = cas non couvert par la procédure standard"),

    ("D-NON",
     "J'ai une dépense imprévue.\nQue faire si mon responsable refuse ma demande de révision budgétaire ?",
     "Que faire en cas de dépense imprévue ?",
     False,
     "suivi : recours après refus hiérarchique ≠ démarche initiale de constat budgétaire"),

    ("D-NON",
     "Peut-on faire un engagement en monnaie étrangère ?\n"
     "Et si la facture finale inclut une majoration liée à la variation du taux de change ?",
     "Peut-on faire une demande d'engagement en monnaie étrangère ?",
     False,
     "suivi : risque de change sur la facture finale = problème comptable distinct de la règle d'engagement"),

    ("D-NON",
     "Comment faire un service fait ?\nEt si une partie de la livraison est endommagée ou non conforme à réception ?",
     "Comment constater un service fait pour une livraison conforme ?",
     False,
     "suivi : réception avec réserves = procédure de réclamation, différente du service fait simple"),

    ("D-NON",
     "Faut-il un engagement pour la médecine de prévention ?\n"
     "Et si la facture de la visite médicale arrive avant la visite elle-même ?",
     "Faut-il faire un engagement de dépense pour la médecine de prévention ?",
     False,
     "suivi : facturation anticipée = cas hors procédure habituelle, non couvert par la FAQ"),

    ("D-NON",
     "Comment récupérer un reliquat d'engagement ?\n"
     "Et si l'engagement a été réalisé sur l'exercice budgétaire de l'année précédente ?",
     "Comment récupérer le reliquat d'un engagement partiellement utilisé ?",
     False,
     "suivi : engagement année N-1 (impossible, restitution uniquement sur l'année courante)"),

    ("D-NON",
     "Ma facture n'est pas réglée.\nEt si le fournisseur menace de saisir le tribunal de commerce faute de paiement ?",
     "Que faire si une facture n'est pas réglée et que le fournisseur relance ?",
     False,
     "suivi : contentieux judiciaire = procédure juridique, hors périmètre du service facturier"),

    ("D-NON",
     "Comment faire un engagement de dépense ?\n"
     "Et si le montant de la commande dépasse mon niveau de délégation de signature ?",
     "Quelle est la procédure pour faire un engagement de dépense ?",
     False,
     "suivi : dépassement de délégation = escalade hiérarchique obligatoire, procédure différente"),
]


# ── Exécution ──────────────────────────────────────────────────────────────────

def main():
    resultats = []
    total = len(CAS)

    print(f"\nLancement de {total} appels Albert — domaine DFE/Finances")
    print("(court-circuit typographique si répétition exacte)\n")

    for i, (cat, posee, indexee, attendu, desc) in enumerate(CAS, 1):
        print(f"[{i:02d}/{total}] {cat} — {desc}…", end=" ", flush=True)
        try:
            est_suivi = cat.startswith("C") or cat.startswith("D")
            obtenu = approuver(posee, indexee, est_suivi=est_suivi)
            ok = obtenu == attendu
            statut = "✅" if ok else "❌"
            print(f"{statut}  (attendu={'OUI' if attendu else 'NON'}, obtenu={'OUI' if obtenu else 'NON'})")
        except Exception as exc:
            ok = False
            obtenu = None
            print(f"💥  ERREUR : {exc}")
        resultats.append((cat, desc, attendu, obtenu, ok))

    # ── Récapitulatif ──────────────────────────────────────────────────────────
    print("\n" + "═" * 72)
    print("RÉCAPITULATIF — FAQ DFE/Finances ONaCVG")
    print("═" * 72)

    cats = {"A-NON": [], "B-OUI": [], "C-OUI": [], "D-NON": []}
    for cat, desc, attendu, obtenu, ok in resultats:
        cats[cat].append((desc, attendu, obtenu, ok))

    labels = {
        "A-NON": "Questions proches mais DIFFÉRENTES  → attendu RAG",
        "B-OUI": "Questions ÉQUIVALENTES               → attendu CANONIQUE",
        "C-OUI": "Précisions PROCHES (fil complet)     → attendu CANONIQUE",
        "D-NON": "Précisions ÉLOIGNÉES (fil complet)   → attendu RAG",
    }

    total_ok = 0
    for cat, label in labels.items():
        cas_cat = cats[cat]
        n_ok = sum(1 for *_, ok in cas_cat if ok)
        total_ok += n_ok
        print(f"\n{label}")
        print(f"  Résultat : {n_ok}/{len(cas_cat)}")
        echecs = [(desc, att, obt) for desc, att, obt, ok in cas_cat if not ok]
        for desc, att, obt in echecs:
            print(f"  ❌  {desc}  (attendu={'OUI' if att else 'NON'}, obtenu={'OUI' if obt else 'NON'})")

    print(f"\n{'═' * 72}")
    print(f"TOTAL : {total_ok}/{total}  ({'✅ TOUT OK' if total_ok == total else '❌ ÉCHECS'})")
    print("═" * 72 + "\n")

    # ── Risques prioritaires ───────────────────────────────────────────────────
    faux_positifs = [(desc, att, obt) for cat, desc, att, obt, ok in resultats
                     if not ok and att is False and obt is True]
    if faux_positifs:
        print("⚠️  FAUX POSITIFS (réponse servie à tort sans revue humaine) :")
        for desc, _, _ in faux_positifs:
            print(f"   - {desc}")
        print()


if __name__ == "__main__":
    main()
