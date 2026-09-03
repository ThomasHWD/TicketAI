"""Test en conditions réelles du garde du cache canonique.

Appelle Albert directement via approuver() — nécessite ALBERT_API_KEY dans .env.
Pas de base de données, pas de Qdrant.

Usage :
    PYTHONPATH=. python scripts/test_garde_reel.py
"""

from app.services.garde_cache import approuver

# ── Format des cas ─────────────────────────────────────────────────────────────
# (categorie, question_posee, question_indexee, attendu_bool, description)

CAS = [
    # ── Catégorie A : proche mais DIFFÉRENT → doit aller en RAG (attendu=False) ──
    ("A-NON", "Combien de jours de congés ai-je ?", "Combien de jours de RTT ai-je ?", False,
     "congés ≠ RTT"),
    ("A-NON", "Puis-je télétravailler ?", "Puis-je refuser de télétravailler ?", False,
     "demande vs refus"),
    ("A-NON", "Quel est le préavis en CDI ?", "Quel est le préavis en CDD ?", False,
     "CDI ≠ CDD"),
    ("A-NON", "Combien de jours de télétravail par semaine ?", "Combien de jours de télétravail par mois ?", False,
     "semaine ≠ mois"),
    ("A-NON", "Quels sont les avantages salariés ?", "Quels sont les avantages pour les stagiaires ?", False,
     "salariés ≠ stagiaires"),
    ("A-NON",
     "Quel est le taux de remboursement des frais de transport ?",
     "Quel est le taux de remboursement des frais de repas ?", False,
     "transport ≠ repas"),
    ("A-NON", "Puis-je bénéficier d'une formation ?", "Mon employeur peut-il me refuser une formation ?", False,
     "droit vs refus de l'employeur"),
    ("A-NON",
     "Quelle est la durée du préavis pour une démission ?",
     "Quelle est la durée du préavis pour un licenciement ?", False,
     "démission ≠ licenciement"),
    ("A-NON",
     "Combien d'heures supplémentaires puis-je faire ?",
     "Combien d'heures supplémentaires suis-je obligé de faire ?", False,
     "droit vs obligation"),
    ("A-NON", "Quelle est la durée du congé maternité ?", "Quelle est la durée du congé paternité ?", False,
     "maternité ≠ paternité"),

    # ── Catégorie B : équivalentes → doit être servi CANONIQUE (attendu=True) ────
    ("B-OUI", "Combien de jours de congés ai-je ?", "Quel est mon nombre de jours de congés annuels ?", True,
     "reformulation simple"),
    ("B-OUI", "Comment demander du télétravail ?", "Quelle est la procédure pour demander le télétravail ?", True,
     "même demande, tournure différente"),
    ("B-OUI",
     "Comment signaler un accident du travail ?",
     "Quelle est la procédure pour déclarer un accident de travail ?", True,
     "signaler = déclarer"),
    ("B-OUI",
     "Mon employeur peut-il modifier mon contrat ?",
     "Est-ce que l'entreprise peut changer les termes de mon contrat ?", True,
     "même sens"),
    ("B-OUI", "Comment obtenir mon bulletin de salaire ?", "Où trouver ma fiche de paie ?", True,
     "bulletin de salaire = fiche de paie"),
    ("B-OUI", "Quelle est la durée de la période d'essai ?", "La période d'essai dure combien de temps ?", True,
     "inversion syntaxique"),
    ("B-OUI", "Puis-je cumuler plusieurs emplois ?", "Est-il possible d'avoir un second emploi en parallèle ?", True,
     "cumul = second emploi"),
    ("B-OUI",
     "Quel est le délai pour contester une sanction disciplinaire ?",
     "J'ai reçu une sanction, combien de temps ai-je pour la contester ?", True,
     "reformulation à la première personne"),
    ("B-OUI",
     "Quels documents fournir pour mon embauche ?",
     "Quelles pièces justificatives apporter lors de mon entrée dans l'entreprise ?", True,
     "documents = pièces justificatives"),
    ("B-OUI",
     "Comment fonctionne la mutuelle d'entreprise ?",
     "À quoi sert la mutuelle proposée par l'employeur ?", True,
     "même objet"),

    # ── Catégorie C : précisions PROCHES (fil = Q initiale + précision) → OUI ───
    # question_posee = fil complet, question_indexee = réponse indexée correspondante
    ("C-OUI", "Quel est le préavis de licenciement ?\nEt pour un apprenti ?",
     "Quel est le préavis de licenciement pour un apprenti ?", True,
     "suivi : précision sur la population"),
    ("C-OUI", "Comment fonctionne le télétravail ?\nCombien de jours maximum par semaine ?",
     "Quel est le nombre maximum de jours de télétravail par semaine ?", True,
     "suivi : extraction d'un chiffre"),
    ("C-OUI", "Quels sont mes droits en cas de licenciement ?\nEt si je suis en CDD ?",
     "Quels sont mes droits en cas de licenciement en CDD ?", True,
     "suivi : restriction au CDD"),
    ("C-OUI", "Puis-je bénéficier d'une formation ?\nQui prend en charge les frais ?",
     "Qui finance les formations professionnelles des salariés ?", True,
     "suivi : question sur le financement"),
    ("C-OUI", "Comment signaler un accident du travail ?\nDans quel délai ?",
     "Quel est le délai pour déclarer un accident du travail ?", True,
     "suivi : délai"),
    ("C-OUI", "Combien de jours de congés ai-je ?\nEt si j'ai moins d'un an d'ancienneté ?",
     "Combien de jours de congés pour un salarié avec moins d'un an d'ancienneté ?", True,
     "suivi : condition d'ancienneté"),
    ("C-OUI", "Comment obtenir un arrêt maladie ?\nQue doit-il contenir ?",
     "Quelles informations doit comporter un arrêt maladie ?", True,
     "suivi : contenu du document"),
    ("C-OUI", "Quelle est la durée du congé maternité ?\nEt pour le père ?",
     "Quelle est la durée du congé paternité ?", True,
     "suivi : changement de bénéficiaire explicite"),
    ("C-OUI", "Puis-je partir en retraite anticipée ?\nÀ partir de quel âge ?",
     "Quel est l'âge minimum pour bénéficier d'une retraite anticipée ?", True,
     "suivi : extraction d'un critère"),
    ("C-OUI", "Quels sont mes avantages en tant que salarié ?\nEt pour les tickets restaurant ?",
     "Comment fonctionnent les tickets restaurant pour les salariés ?", True,
     "suivi : zoom sur un avantage"),

    # ── Catégorie D : précisions ÉLOIGNÉES (fil) → doit aller en RAG (attendu=False) ──
    ("D-NON", "Quel est le préavis de licenciement ?\nEt si je suis en période d'essai ?",
     "Quel est le préavis de licenciement pour un CDI confirmé ?", False,
     "suivi : période d'essai ≠ CDI confirmé"),
    ("D-NON", "Comment fonctionne le télétravail ?\nPuis-je refuser de télétravailler ?",
     "Comment faire une demande de télétravail ?", False,
     "suivi : refus ≠ demande"),
    ("D-NON",
     "Quels sont mes droits en cas de licenciement ?\nMon employeur peut-il me licencier pendant mon arrêt maladie ?",
     "Quels sont mes droits en cas de licenciement économique ?", False,
     "suivi : condition spécifique hors scope"),
    ("D-NON", "Combien de jours de congés ai-je ?\nEt si je travaille à mi-temps ?",
     "Combien de jours de congés pour un temps plein ?", False,
     "suivi : mi-temps ≠ temps plein"),
    ("D-NON", "Quelle est la durée du congé maternité ?\nEst-ce que je peux le prolonger ?",
     "Quelle est la durée légale du congé maternité ?", False,
     "suivi : prolongation ≠ durée légale"),
    ("D-NON", "Comment obtenir un arrêt maladie ?\nEt si c'est pour enfant malade ?",
     "Comment obtenir un arrêt maladie pour soi-même ?", False,
     "suivi : enfant malade ≠ soi-même"),
    ("D-NON", "Quels avantages pour les salariés ?\nEt pour les salariés en CDD ?",
     "Quels avantages pour les salariés en CDI ?", False,
     "suivi : CDD ≠ CDI"),
    ("D-NON", "Puis-je cumuler plusieurs emplois ?\nEt si mon contrat l'interdit ?",
     "Puis-je cumuler plusieurs emplois librement ?", False,
     "suivi : clause contractuelle change la question"),
    ("D-NON", "Quel est le délai pour contester une sanction ?\nEt pour une mise à pied conservatoire ?",
     "Quel est le délai pour contester une sanction disciplinaire ordinaire ?", False,
     "suivi : mise à pied conservatoire ≠ sanction disciplinaire"),
    ("D-NON", "Comment demander une augmentation ?\nQue faire si mon manager refuse ?",
     "Quelle est la procédure pour demander une augmentation de salaire ?", False,
     "suivi : recours après refus ≠ demande initiale"),
]

# ── Exécution ──────────────────────────────────────────────────────────────────

def main():
    resultats = []
    total = len(CAS)

    print(f"\nLancement de {total} appels Albert ({total} appels LLM max, court-circuit si répétition exacte)…\n")

    for i, (cat, posee, indexee, attendu, desc) in enumerate(CAS, 1):
        print(f"[{i:02d}/{total}] {cat} — {desc}…", end=" ", flush=True)
        try:
            obtenu = approuver(posee, indexee)
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
    print("RÉCAPITULATIF")
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


if __name__ == "__main__":
    main()
