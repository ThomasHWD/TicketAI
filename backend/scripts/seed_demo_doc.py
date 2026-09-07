"""Jeu de données de démonstration pour les captures de documentation.

Crée des tickets et des réponses couvrant tous les états visibles de l'interface
(badges, onglets Canoniques / À relire / Obsolètes, angles morts, satisfaction).

Les identifiants sont **déterministes** (uuid5) : relancer le script est
idempotent, et `--purger` supprime exactement ce qu'il a créé, rien d'autre.

    PYTHONPATH=. python scripts/seed_demo_doc.py            # crée / met à jour
    PYTHONPATH=. python scripts/seed_demo_doc.py --indexer   # + indexation Qdrant
    PYTHONPATH=. python scripts/seed_demo_doc.py --purger   # supprime

⚠️  Écrit dans la base de développement. Par défaut, n'écrit **rien dans Qdrant** :
toutes les vues visées sont des requêtes PostgreSQL pures.

⚠️  Conséquence à connaître : sans `--indexer`, les réponses marquées
`canonique=True` ici ne sont **pas** indexées, donc `trouver_reponse_reutilisable`
ne les trouvera jamais et la branche CANONIQUE est inatteignable sur ce jeu de
données. C'est sans effet sur les captures, mais tout test du cache sémantique
mené sur ces données mesurerait le vide. `--indexer` fait passer les réponses
VALIDÉE par le vrai `feedback_job` et lève cette limite, au prix d'un appel
d'embedding Albert par réponse.
"""

import os
import sys
import uuid
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.models.document import Document
from app.models.document_version import DocumentVersion
from app.models.notification import Notification
from app.models.reponse import Reponse
from app.models.ticket import Ticket
from app.models.user import User

NS = uuid.UUID("11111111-2222-3333-4444-555555555555")
DOMAINE = "IT"


def sid(cle: str) -> uuid.UUID:
    return uuid.uuid5(NS, cle)


def now():
    return datetime.now(timezone.utc)


# (clé, objet, question, statut_ticket, statut_job, canonique, jours, notes, closed)
TICKETS = [
    ("t-nouvelle", "Demande d'accès au VPN",
     "Comment obtenir un accès VPN pour le télétravail ?", "NOUVEAU", "TERMINÉ", False, 0, None, False),
    ("t-encours", "Réinitialisation de mot de passe",
     "J'ai oublié mon mot de passe de session, comment le réinitialiser ?",
     "NOUVEAU", "EN_COURS", False, 0, None, False),
    ("t-suggestion", "Renouvellement du poste de travail",
     "Au bout de combien de temps mon ordinateur portable est-il remplacé ?",
     "RÉPONDU", "TERMINÉ", False, 1, None, False),
    ("t-horsdomaine", "Prime de transport",
     "Ai-je droit à une prime de transport pour mes trajets domicile-travail ?",
     "RÉPONDU", "TERMINÉ", False, 2, None, False),
    ("t-horsdomaine2", "Jours de congés supplémentaires",
     "Combien de jours de congés d'ancienneté puis-je poser cette année ?",
     "RÉPONDU", "TERMINÉ", False, 3, None, False),
    ("t-validee", "Installation d'un logiciel métier",
     "Puis-je installer moi-même un logiciel sur mon poste ?", "VALIDÉ", "TERMINÉ", False, 4, (5, 5), False),
    ("t-canonique", "Valeur du ticket restaurant",
     "Quelle est la valeur des tickets restaurant ?", "VALIDÉ", "TERMINÉ", True, 5, (4, 5), False),
    ("t-rejetee", "Question mal formulée",
     "Est-ce que ça marche ?", "REJETÉ", "TERMINÉ", False, 6, None, True),
    ("t-cloture", "Configuration de la messagerie mobile",
     "Comment configurer ma messagerie professionnelle sur mon téléphone ?",
     "VALIDÉ", "TERMINÉ", False, 9, (2, 3), True),
    ("t-canonique2", "Sauvegarde des fichiers",
     "Mes documents sont-ils sauvegardés automatiquement ?", "VALIDÉ", "TERMINÉ", True, 12, (5, 4), True),
]


def purger(db):
    cles_t = [c for c, *_ in TICKETS]
    ids_t = [sid(c) for c in cles_t]
    ids_r = [sid(f"r-{c}") for c in cles_t]
    n_notif = db.query(Notification).filter(Notification.reponse_id.in_(ids_r)).delete(synchronize_session=False)
    n_rep = db.query(Reponse).filter(Reponse.id.in_(ids_r)).delete(synchronize_session=False)
    n_tic = db.query(Ticket).filter(Ticket.id.in_(ids_t)).delete(synchronize_session=False)
    db.commit()
    print(f"Purge : {n_tic} ticket(s), {n_rep} réponse(s), {n_notif} notification(s).")


def main():
    purge = "--purger" in sys.argv
    db = SessionLocal()
    try:
        if purge:
            purger(db)
            return

        demandeur = db.query(User).filter(User.email == "gest.test@ticketai.local").first()
        validateur = db.query(User).filter(User.role == "ADMIN").first()
        if demandeur is None:
            sys.exit("Utilisateur gest.test@ticketai.local introuvable.")
        doc = db.query(Document).filter(Document.domaine == DOMAINE).first()
        doc_id = doc.doc_id if doc else None
        doc_version = doc.version if doc else 1

        # Diff de version : alimente le bandeau « document mis à jour » de l'onglet
        # À relire. Sans lui, l'interface affiche « détail non conservé ».
        if doc_id:
            v = (
                db.query(DocumentVersion)
                .filter(DocumentVersion.doc_id == doc_id, DocumentVersion.version == doc_version)
                .first()
            )
            if v is not None:
                v.changements = {
                    "diff_analysable": True,
                    "nb_unites": 2,
                    "unites": [],
                    "nb_ajoutes": 1,
                    "extraits_ajoutes": [
                        "Toute installation de logiciel est soumise à validation de la DSI, "
                        "à l'exception des logiciels libres inscrits au catalogue.",
                    ],
                    "nb_retires": 1,
                    "extraits_retires": [
                        "Toute installation de logiciel est soumise à validation de la DSI.",
                    ],
                }
                db.merge(v)

        # Réponse de secours si aucun admin n'existe : le demandeur valide.
        vid = (validateur or demandeur).id

        for cle, objet, question, statut_t, statut_j, canonique, jours, notes, closed in TICKETS:
            cree = now() - timedelta(days=jours, hours=2)
            tid = sid(cle)
            t = db.get(Ticket, tid) or Ticket(id=tid)
            t.question, t.objet, t.domaine = question, objet, DOMAINE
            t.user_id = demandeur.id
            t.job_id = sid(f"j-{cle}")
            t.statut_job, t.statut_ticket, t.canonique = statut_j, statut_t, canonique
            t.created_at = cree
            t.processed_at = cree + timedelta(minutes=1) if statut_j == "TERMINÉ" else None
            t.validated_at = cree + timedelta(hours=1) if statut_t == "VALIDÉ" else None
            t.closed_at = cree + timedelta(hours=3) if closed else None
            t.note_qualite, t.note_delai = notes if notes else (None, None)
            t.occurence = 3 if canonique else 0
            db.merge(t)

            if statut_t == "NOUVEAU" and statut_j != "TERMINÉ":
                continue  # ticket en cours de traitement : pas encore de réponse

            rid = sid(f"r-{cle}")
            r = db.get(Reponse, rid) or Reponse(id=rid)
            r.ticket_id = tid
            r.created_at = cree + timedelta(minutes=1)
            r.reponse_source_id = None
            r.obsolete, r.a_relire = False, False
            r.obsolete_raison = r.obsolete_doc_id = r.obsolete_version = r.obsolete_at = None
            r.a_relire_raison = r.a_relire_doc_id = r.a_relire_version = r.a_relire_at = None
            r.analyse_justification = r.analyse_extraits = None
            r.raison_rejet = r.contenu_corrige = None
            r.nb_validations, r.canonique = 0, False
            r.validator_id = r.validated_at = None

            if cle == "t-nouvelle":
                r.contenu = ("La demande d'accès VPN se fait via le portail interne, rubrique « Mes demandes ». "
                             "Elle doit être validée par votre responsable hiérarchique, puis par la DSI. "
                             "Le délai de traitement est de 48 heures ouvrées.")
                r.statut, r.source, r.score_similarite = "EN_ATTENTE", "LLM", 0.61
            elif cle == "t-suggestion":
                r.contenu = ("Le parc informatique est renouvelé tous les quatre ans. "
                             "Un remplacement anticipé est possible en cas de panne matérielle "
                             "non réparable, sur diagnostic de la DSI.")
                r.statut, r.source, r.score_similarite = "EN_ATTENTE", "SUGGESTION", 0.87
            elif cle.startswith("t-horsdomaine"):
                r.contenu = ("Cette question ne relève pas des documents disponibles dans ce domaine. "
                             "Elle a été transmise pour traitement manuel.")
                r.statut, r.source, r.score_similarite = "EN_ATTENTE", "HORS_DOMAINE", 0.22
            elif cle == "t-rejetee":
                r.contenu = "La question ne permet pas d'identifier une demande précise."
                r.statut, r.source, r.score_similarite = "REJETÉE", "LLM", 0.18
                r.raison_rejet = ("Question trop vague : impossible de déterminer le sujet. "
                                  "Le demandeur a été invité à reformuler.")
                r.validator_id, r.validated_at = vid, cree + timedelta(hours=1)
            elif cle == "t-validee":
                r.contenu = ("L'installation de logiciels est réservée aux administrateurs. "
                             "Toute demande passe par le catalogue applicatif interne.")
                r.statut, r.source, r.score_similarite = "VALIDÉE", "LLM", 0.74
                r.nb_validations = 2
                r.validator_id, r.validated_at = vid, cree + timedelta(hours=1)
                # Signalée à relire : le document source a changé.
                if doc_id:
                    r.a_relire, r.a_relire_raison = True, "CONTREDITE_PROBABLE"
                    r.a_relire_doc_id, r.a_relire_version = doc_id, doc_version
                    r.a_relire_at = now() - timedelta(hours=6)
                    r.analyse_justification = (
                        "Le passage modifié introduit une exception pour les logiciels libres "
                        "référencés, que la réponse ne mentionne pas. La contradiction est probable "
                        "mais indirecte : la réponse ne cite pas explicitement ce document."
                    )
                    r.analyse_extraits = {"unites": [{
                        "sens": "MODIFIE",
                        "avant": "Toute installation de logiciel est soumise à validation de la DSI.",
                        "apres": ("Toute installation de logiciel est soumise à validation de la DSI, "
                                  "à l'exception des logiciels libres inscrits au catalogue."),
                    }]}
            elif cle == "t-canonique":
                r.contenu = ("La valeur faciale du ticket restaurant est de 9,00 € par journée travaillée. "
                             "La part employeur s'élève à 4,50 €, soit 50 % de la valeur faciale.")
                r.statut, r.source, r.score_similarite = "VALIDÉE", "LLM", 0.93
                r.nb_validations, r.canonique = 4, True
                r.validator_id, r.validated_at = vid, cree + timedelta(hours=1)
            elif cle == "t-canonique2":
                r.contenu = ("Les dossiers du lecteur réseau personnel sont sauvegardés chaque nuit, "
                             "avec une rétention de 30 jours. Les fichiers stockés sur le bureau local "
                             "ne sont pas sauvegardés.")
                r.statut, r.source, r.score_similarite = "VALIDÉE", "LLM", 0.95
                r.nb_validations, r.canonique = 3, True
                r.validator_id, r.validated_at = vid, cree + timedelta(hours=1)
            elif cle == "t-cloture":
                r.contenu = ("La messagerie se configure via l'application Outlook mobile, "
                             "en saisissant votre adresse professionnelle puis en validant "
                             "l'authentification à deux facteurs.")
                r.statut, r.source, r.score_similarite = "VALIDÉE", "LLM", 0.71
                r.nb_validations = 1
                r.validator_id, r.validated_at = vid, cree + timedelta(hours=1)
                # Retirée du service après mise à jour du document.
                if doc_id:
                    r.obsolete, r.obsolete_raison = True, "CONTREDITE_PAR_MAJ"
                    r.obsolete_doc_id, r.obsolete_version = doc_id, doc_version
                    r.obsolete_at = now() - timedelta(days=1)
                    r.analyse_justification = (
                        "La nouvelle version impose l'application « Mobile Mail » à la place d'Outlook "
                        "mobile. La réponse cite explicitement le passage modifié : elle est contredite."
                    )
                    r.analyse_extraits = {"unites": [{
                        "sens": "MODIFIE",
                        "avant": "La messagerie mobile se configure via Outlook mobile.",
                        "apres": "La messagerie mobile se configure via l'application Mobile Mail.",
                    }]}
            db.merge(r)

        db.commit()
        print(f"{len(TICKETS)} tickets de démonstration créés/mis à jour dans le domaine {DOMAINE}.")

        if "--indexer" in sys.argv:
            # Le vrai `feedback_job`, et non une écriture directe : c'est lui qui
            # pose le point Qdrant portant `reponse_id`, sans lequel une réponse
            # canonique reste invisible du cache.
            from app.workers.feedback import feedback_job

            indexees = 0
            for cle, *_ in TICKETS:
                r = db.get(Reponse, sid(f"r-{cle}"))
                if r is not None and r.statut == "VALIDÉE" and not r.obsolete:
                    feedback_job.apply(args=[str(r.id)]).get()
                    indexees += 1
            print(f"{indexees} réponse(s) validée(s) indexée(s) dans Qdrant.")
        else:
            print("Sans --indexer : rien dans Qdrant, la branche CANONIQUE reste inatteignable.")

        print("Purge : PYTHONPATH=. python scripts/seed_demo_doc.py --purger")
    finally:
        db.close()


if __name__ == "__main__":
    main()
