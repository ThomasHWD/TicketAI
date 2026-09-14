"""Seed de réponses canoniques taguées pour tester le TagCombobox.

Les tags sont générés par le vrai LLM via suggerer_tag (conditions réelles).
Crée des tickets et réponses validées couvrant le document test-avantages-v1,
avec plusieurs réponses par thème pour vérifier le regroupement dans le combobox.

Usage :
    PYTHONPATH=. python scripts/seed_tag_test.py

Les entrées déjà présentes sont ignorées (idempotent sur la question+domaine).
Pour regénérer les tags des réponses existantes, utiliser --retag :
    PYTHONPATH=. python scripts/seed_tag_test.py --retag
"""

import sys
import uuid
from datetime import datetime, timezone

from app.database import SessionLocal
from app.models.reponse import Reponse
from app.models.ticket import Ticket
from app.models.user import User
from app.services.tag_suggestion import suggerer_tag

DOMAINE = "TEST"
ADMIN_EMAIL = "thomas.henwood@onacvg.fr"

# (question, réponse)  — le tag sera généré par le LLM
DONNEES = [
    # ticket restaurant
    (
        "Quelle est la valeur faciale du titre-restaurant ?",
        (
            "Le titre-restaurant a une valeur faciale de 9,00 € par journée de travail "
            "effectif de plus de 4 heures. L'employeur prend en charge 50 % soit 4,50 €, "
            "et la même somme est prélevée sur votre rémunération nette."
        ),
    ),
    (
        "Comment fonctionne la carte Swile pour les titres-restaurant ?",
        (
            "Les titres-restaurant sont dématérialisés sur la carte Swile, rechargée le "
            "premier jour ouvré de chaque mois pour les journées travaillées du mois "
            "précédent. La carte est acceptée 7 j/7 dans tout restaurant, boulangerie "
            "ou épicerie affiliée au réseau Swile."
        ),
    ),
    (
        "Que faire en cas de perte ou de vol de ma carte Swile ?",
        (
            "En cas de perte ou de vol, contactez le service Swile dans les 24 heures "
            "pour faire opposition. Un duplicata est émis sans frais sous 5 jours ouvrés."
        ),
    ),
    # transport
    (
        "L'entreprise rembourse-t-elle mon abonnement aux transports en commun ?",
        (
            "Oui, l'entreprise prend en charge 50 % du coût de votre abonnement mensuel "
            "aux transports en commun (RATP, SNCF Transilien, TER, abonnements combinés). "
            "Le remboursement apparaît sur la fiche de paie du mois suivant la présentation "
            "du justificatif, déposé via le portail RH avant le 5 du mois."
        ),
    ),
    (
        "Puis-je être remboursé si je viens au travail à vélo ?",
        (
            "Oui, une indemnité kilométrique de 0,25 €/km est versée pour les trajets "
            "domicile-travail à vélo ou trottinette. Elle est plafonnée à 800 €/an. "
            "Ce cumul est impossible si vous bénéficiez déjà du remboursement transports "
            "en commun ou d'un véhicule de fonction."
        ),
    ),
    (
        "Comment déclarer mon abonnement annuel SNCF pour obtenir le remboursement mensuel ?",
        (
            "Pour un forfait annuel, déposez votre justificatif via le portail RH > "
            "Remboursements avant le 5 du mois. Le service paie calcule un prorata sur "
            "12 mensualités et rembourse 50 % chaque mois."
        ),
    ),
    # congés
    (
        "Combien de jours de congés payés ai-je par an ?",
        (
            "Les salariés bénéficient de 25 jours ouvrés de congés payés par année de "
            "référence (du 1er juin au 31 mai). Chaque mois complet de travail effectif "
            "génère 2,08 jours, arrondis au demi-jour supérieur en fin d'exercice."
        ),
    ),
    (
        "Que deviennent mes congés non pris au 31 mai ?",
        (
            "Les congés non soldés au 31 mai peuvent être versés sur votre compte "
            "épargne-temps (CET) dans la limite de 5 jours par an à votre demande. "
            "Au-delà, les droits non pris sont perdus sauf accord écrit de la direction."
        ),
    ),
    # horaires
    (
        "Quels sont les horaires fixes de présence obligatoire ?",
        (
            "Deux plages de présence obligatoire encadrent la journée : 9h30-12h00 le "
            "matin et 14h00-16h30 l'après-midi. En dehors de ces plages, vous pouvez "
            "arriver entre 8h et 9h30 et repartir entre 16h30 et 19h00."
        ),
    ),
    (
        "Comment sont gérées les heures supplémentaires ?",
        (
            "Tout dépassement au-delà de 35h/semaine constitue des heures supplémentaires "
            "qui nécessitent une demande préalable écrite validée par le responsable. "
            "Elles donnent lieu à récupération dans les 4 semaines suivantes."
        ),
    ),
    # prévoyance / santé
    (
        "Quelle est la part de l'employeur dans la mutuelle ?",
        (
            "L'entreprise prend en charge 60 % de la cotisation de base (couverture "
            "individuelle). Les 40 % restants sont prélevés mensuellement sur votre "
            "rémunération nette. La couverture des ayants droit est facultative."
        ),
    ),
    (
        "À partir de quand la prévoyance prend-elle le relais en cas d'arrêt maladie ?",
        (
            "Le régime de prévoyance prend le relais à compter du 90ème jour d'arrêt "
            "pour maintenir un niveau de revenu complémentaire aux indemnités journalières "
            "de l'Assurance Maladie."
        ),
    ),
    # télétravail
    (
        "Combien de jours de télétravail par semaine puis-je faire ?",
        (
            "Les salariés en CDI ayant validé leur période d'essai peuvent télétravailler "
            "2 jours ouvrés par semaine, le mercredi et le vendredi uniquement. Ces jours "
            "ne peuvent être ni cumulés, ni reportés, ni pris en demi-journées."
        ),
    ),
    (
        "Quel matériel l'entreprise fournit-elle pour le télétravail ?",
        (
            "L'entreprise met à disposition : ordinateur portable, accès VPN sécurisé "
            "et téléphonie sur IP. En cas de dysfonctionnement technique avéré à votre "
            "domicile, le télétravail peut être temporairement suspendu par l'employeur."
        ),
    ),
]


def seed(retag: bool = False) -> None:
    db = SessionLocal()
    try:
        validator = db.query(User).filter(User.email == ADMIN_EMAIL).first()
        if not validator:
            print(f"[ERREUR] Utilisateur {ADMIN_EMAIL} introuvable.")
            return

        now = datetime.now(timezone.utc)
        created = 0

        def _tags_existants() -> list[str] | None:
            rows = (
                db.query(Reponse.tag)
                .join(Ticket, Ticket.id == Reponse.ticket_id)
                .filter(
                    Reponse.tag.isnot(None),
                    Reponse.canonique.is_(True),
                    Reponse.obsolete.is_(False),
                    Ticket.domaine == DOMAINE,
                )
                .distinct()
                .all()
            )
            return sorted(r.tag for r in rows) or None

        for question, contenu in DONNEES:
            existing_ticket = db.query(Ticket).filter(
                Ticket.question == question,
                Ticket.domaine == DOMAINE,
            ).first()

            if existing_ticket and not retag:
                r = db.query(Reponse).filter(Reponse.ticket_id == existing_ticket.id).first()
                print(f"= existe déjà (tag={r.tag if r else '?'}) : {question[:50]}…")
                continue

            if existing_ticket and retag:
                r = db.query(Reponse).filter(Reponse.ticket_id == existing_ticket.id).first()
                if r:
                    old = r.tag
                    r.tag = suggerer_tag(question, contenu, db, _tags_existants())
                    db.flush()
                    print(f"~ retag {old!r} → {r.tag!r} : {question[:50]}…")
                continue

            tags = _tags_existants()
            print(f"  Génération du tag pour : {question[:55]}…", end=" ", flush=True)
            tag = suggerer_tag(question, contenu, db, tags)
            print(f"→ {tag!r}")

            ticket = Ticket(
                id=uuid.uuid4(),
                question=question,
                domaine=DOMAINE,
                user_id=None,
                statut_job="TERMINÉ",
                statut_ticket="VALIDÉ",
                masque_angles_morts=False,
            )
            db.add(ticket)
            db.flush()

            reponse = Reponse(
                id=uuid.uuid4(),
                ticket_id=ticket.id,
                contenu=contenu,
                statut="VALIDÉE",
                source="LLM",
                nb_validations=3,
                canonique=True,
                obsolete=False,
                tag=tag,
                validator_id=validator.id,
                validated_at=now,
                created_at=now,
            )
            db.add(reponse)
            created += 1

        db.commit()
        print(f"\n✓ {created} réponse(s) créée(s).")
    finally:
        db.close()


if __name__ == "__main__":
    seed(retag="--retag" in sys.argv)
