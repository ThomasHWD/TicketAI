"""Bilan consolidé du garde du cache canonique.

Combine :
  - 80 résultats déjà obtenus (HR/IT + DFE, quota économisé)
  - 60 nouveaux cas à exécuter maintenant

Usage :
    PYTHONPATH=. python scripts/test_garde_bilan.py
"""

from app.services.garde_cache import approuver

# ── Résultats des deux passes précédentes (quota déjà consommé) ────────────
# Format : (domaine_jeu, cat, desc, attendu, obtenu)
RESULTATS_PRECEDENTS = [
    # ── Jeu HR/IT ──────────────────────────────────────────────────────────
    ("HR/IT", "A-NON", "congés ≠ RTT", False, False),
    ("HR/IT", "A-NON", "demande vs refus", False, False),
    ("HR/IT", "A-NON", "CDI ≠ CDD", False, False),
    ("HR/IT", "A-NON", "semaine ≠ mois", False, False),
    ("HR/IT", "A-NON", "salariés ≠ stagiaires", False, False),
    ("HR/IT", "A-NON", "transport ≠ repas", False, False),
    ("HR/IT", "A-NON", "droit vs refus employeur", False, False),
    ("HR/IT", "A-NON", "démission ≠ licenciement", False, False),
    ("HR/IT", "A-NON", "droit vs obligation HS", False, False),
    ("HR/IT", "A-NON", "maternité ≠ paternité", False, False),
    ("HR/IT", "B-OUI", "reformulation simple", True, False),       # FN
    ("HR/IT", "B-OUI", "même demande, tournure différente", True, True),
    ("HR/IT", "B-OUI", "signaler = déclarer", True, True),
    ("HR/IT", "B-OUI", "même sens", True, True),
    ("HR/IT", "B-OUI", "bulletin de salaire = fiche de paie", True, True),
    ("HR/IT", "B-OUI", "inversion syntaxique", True, True),
    ("HR/IT", "B-OUI", "cumul = second emploi", True, True),
    ("HR/IT", "B-OUI", "reformulation 1ère personne", True, True),
    ("HR/IT", "B-OUI", "documents = pièces justificatives", True, True),
    ("HR/IT", "B-OUI", "même objet", True, False),                 # FN
    ("HR/IT", "C-OUI", "suivi : précision sur la population", True, False),    # FN
    ("HR/IT", "C-OUI", "suivi : extraction d'un chiffre", True, False),        # FN
    ("HR/IT", "C-OUI", "suivi : restriction au CDD", True, False),             # FN
    ("HR/IT", "C-OUI", "suivi : question sur le financement", True, False),    # FN
    ("HR/IT", "C-OUI", "suivi : délai", True, False),                          # FN
    ("HR/IT", "C-OUI", "suivi : condition d'ancienneté", True, False),         # FN
    ("HR/IT", "C-OUI", "suivi : contenu du document", True, False),            # FN
    ("HR/IT", "C-OUI", "suivi : changement de bénéficiaire", True, False),     # FN
    ("HR/IT", "C-OUI", "suivi : extraction d'un critère", True, False),        # FN
    ("HR/IT", "C-OUI", "suivi : zoom sur un avantage", True, False),           # FN
    ("HR/IT", "D-NON", "suivi : période d'essai ≠ CDI confirmé", False, False),
    ("HR/IT", "D-NON", "suivi : refus ≠ demande", False, False),
    ("HR/IT", "D-NON", "suivi : condition hors scope", False, False),
    ("HR/IT", "D-NON", "suivi : mi-temps ≠ temps plein", False, False),
    ("HR/IT", "D-NON", "suivi : prolongation ≠ durée légale", False, False),
    ("HR/IT", "D-NON", "suivi : enfant malade ≠ soi-même", False, False),
    ("HR/IT", "D-NON", "suivi : CDD ≠ CDI", False, False),
    ("HR/IT", "D-NON", "suivi : clause contractuelle", False, False),
    ("HR/IT", "D-NON", "suivi : mise à pied ≠ sanction ordinaire", False, False),
    ("HR/IT", "D-NON", "suivi : recours après refus ≠ demande initiale", False, False),
    # ── Jeu DFE/Finance ────────────────────────────────────────────────────
    ("DFE", "A-NON", "engagement ≠ service fait", False, False),
    ("DFE", "A-NON", "visite médicale ≠ cotisation annuelle", False, False),
    ("DFE", "A-NON", "Siège ≠ service départemental", False, False),
    ("DFE", "A-NON", "reliquat année N-1 ≠ année courante", False, False),
    ("DFE", "A-NON", "annulation complète ≠ restitution partielle", False, False),
    ("DFE", "A-NON", "mail conditions spécifiques ≠ devis standard", False, False),
    ("DFE", "A-NON", "engagement bloqué ≠ facture impayée", False, False),
    ("DFE", "A-NON", "dépense dans budget ≠ hors budget", False, False),
    ("DFE", "A-NON", "bon de commande sans n° ≠ sans mise en concurrence", False, False),
    ("DFE", "A-NON", "subventions CT ≠ bilan budgétaire", False, False),
    ("DFE", "B-OUI", "saisir = faire demande d'engagement", True, True),
    ("DFE", "B-OUI", "devises étrangères = monnaie étrangère", True, True),
    ("DFE", "B-OUI", "formulaire = modèle de CA", True, False),               # FN
    ("DFE", "B-OUI", "fournisseur réclame = facture impayée relance", True, True),
    ("DFE", "B-OUI", "déclarer réception = service fait", True, True),
    ("DFE", "B-OUI", "email justificatif = mail abonnement numérique", True, False),  # FN
    ("DFE", "B-OUI", "rendre crédits = récupérer reliquat", True, False),     # FN
    ("DFE", "B-OUI", "frais mission = frais déplacements", True, True),
    ("DFE", "B-OUI", "subventions collectivités locales = CT", True, True),
    ("DFE", "B-OUI", "médecine du travail = médecine de prévention", True, True),
    ("DFE", "C-OUI", "suivi : engagement action Mémoire", True, True),
    ("DFE", "C-OUI", "suivi : contenu mail facturier", True, True),
    ("DFE", "C-OUI", "suivi : justificatifs en devise", True, True),
    ("DFE", "C-OUI", "suivi : reliquat multi-comptes", True, True),
    ("DFE", "C-OUI", "suivi : cotisation annuelle médecine", True, True),
    ("DFE", "C-OUI", "suivi : soutenabilité avant dépense imprévue", True, False),  # FN
    ("DFE", "C-OUI", "suivi : adresse mail facturier", True, False),          # FN
    ("DFE", "C-OUI", "suivi : responsabilité service fait", True, True),
    ("DFE", "C-OUI", "suivi : Chorus Pro avant mail sfact", True, False),     # FN
    ("DFE", "C-OUI", "suivi : n° engagement sur bon de commande", True, True),
    ("DFE", "D-NON", "suivi : refus bon de commande fournisseur", False, False),
    ("DFE", "D-NON", "suivi : silence du service facturier", False, False),
    ("DFE", "D-NON", "suivi : justificatifs perdus", False, False),
    ("DFE", "D-NON", "suivi : refus hiérarchique budget", False, False),
    ("DFE", "D-NON", "suivi : majoration taux de change", False, True),       # FP !
    ("DFE", "D-NON", "suivi : livraison endommagée", False, False),
    ("DFE", "D-NON", "suivi : facturation anticipée visite", False, False),
    ("DFE", "D-NON", "suivi : reliquat année précédente", False, False),
    ("DFE", "D-NON", "suivi : contentieux judiciaire", False, False),
    ("DFE", "D-NON", "suivi : dépassement délégation signature", False, False),
]

# ── 60 nouveaux cas à exécuter ─────────────────────────────────────────────
# (cat, question_posee, question_indexee, attendu, description, est_suivi)

NOUVEAUX_CAS = [
    # ── A-NON (15) : questions proches mais DIFFÉRENTES ────────────────────
    ("A-NON",
     "Quelle est la durée légale d'une garde à vue ?",
     "Quelle est la durée légale d'une détention provisoire ?",
     False, "garde à vue ≠ détention provisoire", False),

    ("A-NON",
     "Puis-je résilier un contrat par email ?",
     "Puis-je conclure un contrat par email ?",
     False, "résilier ≠ conclure", False),

    ("A-NON",
     "Comment déclarer un arrêt maladie ?",
     "Comment déclarer une maladie professionnelle ?",
     False, "arrêt maladie ≠ maladie professionnelle", False),

    ("A-NON",
     "Quelle est la durée du préavis en cas de démission ?",
     "Quelle est la durée du préavis en cas de rupture conventionnelle ?",
     False, "démission ≠ rupture conventionnelle", False),

    ("A-NON",
     "Comment calculer les congés payés acquis ?",
     "Comment calculer les RTT acquis ?",
     False, "congés payés ≠ RTT", False),

    ("A-NON",
     "Puis-je accéder au VPN depuis l'étranger ?",
     "Puis-je accéder au VPN depuis mon domicile en France ?",
     False, "étranger ≠ domicile France, conditions différentes", False),

    ("A-NON",
     "Comment réinitialiser son mot de passe ?",
     "Comment créer son mot de passe initial ?",
     False, "réinitialiser (existant) ≠ créer (nouveau)", False),

    ("A-NON",
     "Quel est le montant de l'indemnité de licenciement pour un CDI ?",
     "Quel est le montant de l'indemnité de rupture conventionnelle ?",
     False, "licenciement ≠ rupture conventionnelle, calcul différent", False),

    ("A-NON",
     "Comment signaler un phishing reçu par email ?",
     "Comment signaler un spam reçu par email ?",
     False, "phishing (fraude) ≠ spam (publicité), procédures différentes", False),

    ("A-NON",
     "Quelle est la durée de conservation d'un contrat de travail après départ ?",
     "Quelle est la durée de conservation d'une fiche de paie après départ ?",
     False, "contrat de travail ≠ fiche de paie, durées légales différentes", False),

    ("A-NON",
     "Combien de jours de congés pour un salarié à temps partiel ?",
     "Combien de jours de congés pour un salarié à temps plein ?",
     False, "temps partiel ≠ temps plein", False),

    ("A-NON",
     "Quel est le délai de prescription d'une faute disciplinaire ?",
     "Quel est le délai de prescription d'une faute professionnelle ?",
     False, "disciplinaire ≠ professionnelle, régimes distincts", False),

    ("A-NON",
     "Comment fonctionne le remboursement des frais kilométriques en voiture ?",
     "Comment fonctionne le remboursement des frais de transport en commun ?",
     False, "voiture (barème km) ≠ transports en commun (50%)", False),

    ("A-NON",
     "Puis-je cumuler un emploi salarié avec une activité d'auto-entrepreneur ?",
     "Puis-je cumuler deux emplois salariés simultanément ?",
     False, "salarié + auto-entrepreneur ≠ deux salariés, règles différentes", False),

    ("A-NON",
     "Quel est le délai de paiement d'une facture fournisseur en secteur public ?",
     "Quel est le délai de paiement d'une facture fournisseur en secteur privé ?",
     False, "public (30j réglementaire) ≠ privé (60j max)", False),

    # ── B-OUI (15) : reformulations ÉQUIVALENTES ───────────────────────────
    ("B-OUI",
     "Comment contacter le support informatique ?",
     "Quelle est la procédure pour joindre le service IT ?",
     True, "support informatique = service IT, même démarche", False),

    ("B-OUI",
     "Quel est le montant de la prime de fin d'année ?",
     "À combien s'élève la prime annuelle ?",
     True, "prime de fin d'année = prime annuelle", False),

    ("B-OUI",
     "Comment s'inscrire à une formation interne ?",
     "Quelle est la procédure pour participer à une formation de l'entreprise ?",
     True, "s'inscrire = participer, formation interne = formation entreprise", False),

    ("B-OUI",
     "Qui contacter en cas d'accident du travail ?",
     "Quel interlocuteur appeler suite à un accident sur le lieu de travail ?",
     True, "même situation, même interlocuteur", False),

    ("B-OUI",
     "Comment demander une attestation d'emploi ?",
     "Quelle démarche suivre pour obtenir un justificatif de travail ?",
     True, "attestation d'emploi = justificatif de travail", False),

    ("B-OUI",
     "Quel est le délai de carence lors d'un arrêt maladie ?",
     "Combien de jours ne sont pas indemnisés en début d'arrêt maladie ?",
     True, "délai de carence = jours non indemnisés au début", False),

    ("B-OUI",
     "Comment mettre à jour son RIB pour le virement de salaire ?",
     "Quelle procédure pour changer ses coordonnées bancaires pour la paie ?",
     True, "RIB = coordonnées bancaires, salaire = paie", False),

    ("B-OUI",
     "À qui signaler un comportement inapproprié d'un collègue ?",
     "Qui contacter pour dénoncer un agissement déplacé au travail ?",
     True, "même situation, même question", False),

    ("B-OUI",
     "Quelle est la politique de l'entreprise sur le télétravail ?",
     "Quelles sont les règles applicables au travail à distance ?",
     True, "politique = règles, télétravail = travail à distance", False),

    ("B-OUI",
     "Peut-on combiner télétravail et temps partiel ?",
     "Est-il possible de cumuler travail à distance et contrat à temps partiel ?",
     True, "même question, vocabulaire différent", False),

    ("B-OUI",
     "Comment obtenir son solde de tout compte ?",
     "Quelle procédure pour recevoir le solde de tout compte lors d'un départ ?",
     True, "obtenir = recevoir, même document", False),

    ("B-OUI",
     "Où trouver le formulaire de demande d'engagement ?",
     "Sur quelle page de l'intranet saisir un engagement de dépense ?",
     True, "formulaire = page de saisie, engagement = même chose", False),

    ("B-OUI",
     "Quelles pièces fournir pour une demande de logement social ?",
     "Quels documents joindre au dossier de demande de HLM ?",
     True, "logement social = HLM, pièces = documents", False),

    ("B-OUI",
     "Comment calculer l'indemnité de fin de contrat d'un CDD ?",
     "Quel est le montant de la prime de précarité en CDD ?",
     True, "indemnité fin de CDD = prime de précarité, même chose", False),

    ("B-OUI",
     "Quels sont les droits du salarié en arrêt maladie de longue durée ?",
     "Que prévoit la loi pour un employé en congé maladie prolongé ?",
     True, "arrêt maladie longue durée = congé maladie prolongé, droits identiques", False),

    # ── C-OUI (15) : précisions PROCHES en fil ─────────────────────────────
    ("C-OUI",
     "Quel est le délai de carence en maladie ?\nCombien de jours exactement ?",
     "Combien de jours de carence lors d'un arrêt maladie ?",
     True, "suivi : extraction du chiffre exact de carence", True),

    ("C-OUI",
     "Comment déclarer un accident du travail ?\nQuel est le délai pour le faire ?",
     "Quel est le délai de déclaration d'un accident du travail ?",
     True, "suivi : zoom sur le délai de déclaration", True),

    ("C-OUI",
     "Combien de jours de congés ai-je ?\nEt pour un salarié à temps plein ?",
     "Combien de jours de congés annuels pour un salarié à temps plein ?",
     True, "suivi : précision sur le type de contrat (temps plein)", True),

    ("C-OUI",
     "Puis-je télétravailler ?\nCombien de jours par mois au maximum ?",
     "Quel est le nombre maximum de jours de télétravail autorisés par mois ?",
     True, "suivi : extraction du plafond mensuel", True),

    ("C-OUI",
     "Comment faire une demande d'engagement ?\nOù se trouve le formulaire sur l'intranet ?",
     "Où trouver le formulaire de demande d'engagement sur l'intranet ?",
     True, "suivi : localisation du formulaire", True),

    ("C-OUI",
     "Comment signaler une facture impayée ?\nQuel justificatif Chorus Pro dois-je joindre ?",
     "Quel justificatif fournir pour signaler une facture impayée au service facturier ?",
     True, "suivi : pièce à joindre (Chorus Pro)", True),

    ("C-OUI",
     "Qu'est-ce qu'un service fait ?\nQui doit le constater dans les services prescripteurs ?",
     "Qui est responsable de constater le service fait ?",
     True, "suivi : responsabilité de la constatation", True),

    ("C-OUI",
     "Quel est le préavis de licenciement ?\nEt pour un salarié en CDI confirmé ?",
     "Quel est le préavis de licenciement pour un salarié en CDI ?",
     True, "suivi : restriction explicite au CDI confirmé", True),

    ("C-OUI",
     "Comment faire une rupture conventionnelle ?\nQuel est le délai de rétractation ?",
     "Quel est le délai de rétractation dans une rupture conventionnelle ?",
     True, "suivi : extraction du délai de rétractation", True),

    ("C-OUI",
     "Quelles sont mes indemnités de licenciement ?\nComment les calculer ?",
     "Comment calculer les indemnités légales de licenciement ?",
     True, "suivi : méthode de calcul des indemnités", True),

    ("C-OUI",
     "Comment contacter le support IT ?\nQuelle est l'adresse email du service desk ?",
     "Quelle est l'adresse email du support informatique ?",
     True, "suivi : extraction de l'adresse email", True),

    ("C-OUI",
     "Puis-je poser des congés ?\nEn quelle période faut-il les déposer ?",
     "Quelles sont les périodes de dépôt des demandes de congés ?",
     True, "suivi : périodes de dépôt des congés", True),

    ("C-OUI",
     "Comment gérer une note de frais ?\nQuel est le délai pour la soumettre ?",
     "Quel est le délai pour soumettre une note de frais ?",
     True, "suivi : délai de soumission des notes de frais", True),

    ("C-OUI",
     "Quelle est la durée de la période d'essai ?\nEt pour un cadre en CDI ?",
     "Quelle est la durée de la période d'essai pour un cadre en CDI ?",
     True, "suivi : restriction à la catégorie cadre", True),

    ("C-OUI",
     "Comment obtenir mon attestation de salaire ?\nQui la délivre dans l'entreprise ?",
     "Qui délivre les attestations de salaire dans l'entreprise ?",
     True, "suivi : identification de l'interlocuteur", True),

    # ── D-NON (15) : précisions ÉLOIGNÉES en fil ───────────────────────────
    ("D-NON",
     "Quel est le préavis de licenciement ?\nEt si c'est pour faute grave ?",
     "Quel est le préavis de licenciement pour un CDI ?",
     False, "suivi : faute grave = aucun préavis, règle opposée", True),

    ("D-NON",
     "Puis-je télétravailler ?\nEt si mon manager refuse systématiquement sans justification ?",
     "Comment faire une demande de télétravail ?",
     False, "suivi : refus managérial = recours RH, procédure différente", True),

    ("D-NON",
     "Combien de jours de congés ai-je ?\nEt si je tombe malade pendant mes congés posés ?",
     "Combien de jours de congés annuels ai-je droit ?",
     False, "suivi : maladie pendant congés = report, règle distincte", True),

    ("D-NON",
     "Comment déclarer un accident du travail ?\nEt si l'accident s'est produit sur le trajet ?",
     "Comment déclarer un accident du travail survenu sur le lieu de travail ?",
     False, "suivi : accident de trajet ≠ accident du travail, régimes distincts", True),

    ("D-NON",
     "Quelle est la durée de la période d'essai ?\nPeut-elle être renouvelée et dans quelles conditions ?",
     "Quelle est la durée légale de la période d'essai ?",
     False, "suivi : renouvellement = conditions supplémentaires, question différente", True),

    ("D-NON",
     "Puis-je cumuler plusieurs emplois ?\nEt si mon contrat contient une clause d'exclusivité ?",
     "Puis-je avoir un second emploi en parallèle ?",
     False, "suivi : clause d'exclusivité = interdiction contractuelle, cas distinct", True),

    ("D-NON",
     "Comment gérer une note de frais ?\nEt si le montant dépasse le plafond autorisé par la politique ?",
     "Quelle est la procédure pour soumettre une note de frais ?",
     False, "suivi : dépassement de plafond = validation exceptionnelle requise", True),

    ("D-NON",
     "Comment contacter le support IT ?\nEt si le problème est critique en dehors des heures de bureau ?",
     "Quelle est la procédure standard pour contacter le support informatique ?",
     False, "suivi : urgence hors heures = astreinte, procédure différente", True),

    ("D-NON",
     "Quel est le préavis pour une démission ?\nEt si je souhaite partir immédiatement sans effectuer le préavis ?",
     "Quel est le délai de préavis en cas de démission ?",
     False, "suivi : dispense de préavis = accord employeur nécessaire", True),

    ("D-NON",
     "À qui signaler un comportement inapproprié ?\nEt si c'est le manager direct qui est en cause ?",
     "À qui signaler un comportement déplacé d'un collègue au travail ?",
     False, "suivi : manager mis en cause = escalade N+2 ou RH, circuit différent", True),

    ("D-NON",
     "Comment faire un engagement de dépense ?\nEt si le fournisseur n'est pas référencé dans le système ?",
     "Quelle est la procédure pour faire un engagement de dépense ?",
     False, "suivi : fournisseur non référencé = démarche de référencement préalable", True),

    ("D-NON",
     "Comment calculer les indemnités de licenciement ?\nEt si le salarié a moins d'un an d'ancienneté ?",
     "Comment calculer les indemnités légales de licenciement ?",
     False, "suivi : moins d'un an = pas d'indemnité légale, règle opposée", True),

    ("D-NON",
     "Puis-je poser des congés pendant la période d'essai ?\nEt si mon employeur refuse toutes mes demandes ?",
     "Puis-je prendre des congés pendant la période d'essai ?",
     False, "suivi : refus systématique = recours possible, cas différent", True),

    ("D-NON",
     "Quel est le délai de paiement d'une facture ?\nEt si le client conteste le montant facturé ?",
     "Quel est le délai légal de paiement des factures entre professionnels ?",
     False, "suivi : contestation = suspension du délai et procédure de litige", True),

    ("D-NON",
     "Comment mettre à jour mon RIB pour la paie ?\nEt si le changement doit être effectif dès ce mois-ci ?",
     "Quelle procédure pour modifier ses coordonnées bancaires pour le virement de salaire ?",
     False, "suivi : urgence ce mois-ci = délai de traitement paie, contrainte calendaire distincte", True),
]


# ── Exécution des nouveaux cas ─────────────────────────────────────────────

def executer_nouveaux() -> list[tuple]:
    """Exécute les 60 nouveaux cas, retourne les résultats."""
    resultats = []
    total = len(NOUVEAUX_CAS)
    print(f"\nExécution de {total} nouveaux cas…\n")

    for i, (cat, posee, indexee, attendu, desc, est_suivi) in enumerate(NOUVEAUX_CAS, 1):
        print(f"[{i:02d}/{total}] {cat} — {desc}…", end=" ", flush=True)
        try:
            obtenu = approuver(posee, indexee, est_suivi=est_suivi)
            ok = obtenu == attendu
            print(f"{'✅' if ok else '❌'}  ({'OUI' if obtenu else 'NON'})")
        except Exception as exc:
            obtenu = None
            print(f"💥  ERREUR : {exc}")
        resultats.append(("NOUVEAU", cat, desc, attendu, obtenu))

    return resultats


# ── Rapport statistique ────────────────────────────────────────────────────

def rapport(tous: list[tuple]) -> None:
    """Produit le rapport consolidé depuis tous les résultats."""

    # Filtres
    negatifs   = [(d, c, desc, a, o) for d, c, desc, a, o in tous if a is False]
    positifs   = [(d, c, desc, a, o) for d, c, desc, a, o in tous if a is True]
    a_non      = [(d, c, desc, a, o) for d, c, desc, a, o in tous if c == "A-NON"]
    b_oui      = [(d, c, desc, a, o) for d, c, desc, a, o in tous if c == "B-OUI"]
    c_oui      = [(d, c, desc, a, o) for d, c, desc, a, o in tous if c == "C-OUI"]
    d_non      = [(d, c, desc, a, o) for d, c, desc, a, o in tous if c == "D-NON"]

    def taux(cas, attendu):
        """% de cas où le résultat attendu a été obtenu."""
        if not cas:
            return 0, 0, 0.0
        ok = sum(1 for *_, a, o in cas if o == a)
        return ok, len(cas), 100 * ok / len(cas)

    # ── Global ──────────────────────────────────────────────────────────
    total   = len(tous)
    valides = [r for r in tous if r[4] is not None]
    ok_tot  = sum(1 for *_, a, o in valides if o == a)

    # ── Sécurité (faux positifs = cas NON attendu mais OUI obtenu) ──────
    faux_positifs = [(d, c, desc, a, o) for d, c, desc, a, o in negatifs if o is True]
    n_neg  = len(negatifs)
    n_fp   = len(faux_positifs)
    taux_secu = 100 * (n_neg - n_fp) / n_neg if n_neg else 0.0

    # ── Sévérité (faux négatifs = cas OUI attendu mais NON obtenu) ──────
    faux_negatifs = [(d, c, desc, a, o) for d, c, desc, a, o in positifs if o is False]
    n_pos  = len(positifs)
    n_fn   = len(faux_negatifs)
    taux_rec = 100 * (n_pos - n_fn) / n_pos if n_pos else 0.0
    taux_strict = 100 * n_fn / n_pos if n_pos else 0.0

    print("\n" + "═" * 72)
    print("BILAN CONSOLIDÉ DU GARDE DU CACHE CANONIQUE")
    print(f"  {total} cas  ·  {len(RESULTATS_PRECEDENTS)} résultats précédents + {len(NOUVEAUX_CAS)} nouveaux")
    print("═" * 72)

    # ── Métriques principales ────────────────────────────────────────────
    print(f"""
┌─────────────────────────────────────────────────────────────────────┐
│  SÉCURITÉ   : le garde protège contre les mauvaises réponses        │
│  ───────────────────────────────────────────────────────────────    │
│  Taux de sécurité          {taux_secu:5.1f} %   ({n_neg - n_fp}/{n_neg} bonnes refus)     │
│  Faux positifs (danger)    {n_fp:5d}      réponse servie sans revue à tort   │
│                                                                     │
│  SÉVÉRITÉ   : le garde bloque des réponses qui auraient pu passer   │
│  ───────────────────────────────────────────────────────────────    │
│  Taux de reconnaissance    {taux_rec:5.1f} %   ({n_pos - n_fn}/{n_pos} bons approvals)   │
│  Taux de sur-prudence      {taux_strict:5.1f} %   ({n_fn}/{n_pos} refus inutiles)         │
└─────────────────────────────────────────────────────────────────────┘""")

    # ── Par catégorie ────────────────────────────────────────────────────
    print("\nDÉTAIL PAR CATÉGORIE\n")
    print(f"  {'Catégorie':<40} {'OK':>4} {'Total':>6}  {'Taux':>6}  Rôle")
    print(f"  {'-'*40} {'-'*4} {'-'*6}  {'-'*6}  {'-'*30}")

    for label, cas, role in [
        ("A-NON  (questions différentes, sans fil)", a_non, "Sécurité"),
        ("B-OUI  (reformulations équivalentes)",     b_oui, "Sévérité"),
        ("C-OUI  (suivis proches, fil)",             c_oui, "Sévérité"),
        ("D-NON  (suivis éloignés, fil)",            d_non, "Sécurité"),
    ]:
        ok, n, pct = taux(cas, None)
        ok = sum(1 for *_, a, o in cas if o == a)
        pct = 100 * ok / n if n else 0.0
        print(f"  {label:<40} {ok:>4} {n:>6}  {pct:>5.1f}%  {role}")

    # ── Par jeu de données ───────────────────────────────────────────────
    print("\nDÉTAIL PAR DOMAINE\n")
    for domaine in ["HR/IT", "DFE", "NOUVEAU"]:
        sous = [(d, c, desc, a, o) for d, c, desc, a, o in tous if d == domaine]
        if not sous:
            continue
        ok_s = sum(1 for *_, a, o in sous if o == a)
        pct = 100 * ok_s / len(sous)
        fp = sum(1 for *_, a, o in sous if a is False and o is True)
        fn = sum(1 for *_, a, o in sous if a is True and o is False)
        print(f"  {domaine:<10} {ok_s:>3}/{len(sous):<3} ({pct:4.1f}%)  "
              f"FP={fp}  FN={fn}")

    # ── Faux positifs (liste complète) ───────────────────────────────────
    print(f"\nFAUX POSITIFS — réponses servies sans revue à tort ({n_fp} cas)")
    if faux_positifs:
        for d, _c, desc, _a, _o in faux_positifs:
            print(f"  ⚠️  [{d}] {desc}")
    else:
        print("  ✅  Aucun")

    # ── Analyse C-OUI (motif récurrent) ─────────────────────────────────
    c_fn = [(d, c, desc, a, o) for d, c, desc, a, o in c_oui if o is False]
    c_ok = len(c_oui) - len(c_fn)
    print(f"\nANALYSE C-OUI (précisions dans un fil)\n"
          f"  {c_ok}/{len(c_oui)} approuvés — le garde tend à traiter la précision "
          f"comme une demande distincte de la question indexée")

    print("\n" + "═" * 72)
    print(f"VERDICT GLOBAL : {ok_tot}/{total} corrects")
    print(f"  → Sécurité  : {taux_secu:.1f} %  (sur {n_neg} cas de refus attendu)")
    print(f"  → Sévérité  : le garde est trop strict dans {taux_strict:.1f} % "
          f"des cas d'équivalence ({n_fn}/{n_pos})")
    print("═" * 72 + "\n")


# ── Main ───────────────────────────────────────────────────────────────────

def main():
    nouveaux = executer_nouveaux()
    tous = [(d, c, desc, a, o) for d, c, desc, a, o in RESULTATS_PRECEDENTS] + nouveaux
    rapport(tous)


if __name__ == "__main__":
    main()
