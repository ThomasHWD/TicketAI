"""Décide si une réponse déjà servie survit à la nouvelle version d'un document.

C'est le seul endroit du projet où **le texte de la réponse est lu**. Tout le
reste de la chaîne d'obsolescence compare document à document : on sait quels
passages ont fondé une réponse, on vérifie s'ils existent encore. C'est robuste
mais ça ne répond pas à la question qui compte. Un chunk fait 384 tokens ; y
corriger une virgule le rend introuvable en sous-chaîne et condamnait jusqu'ici
une réponse parfaitement juste. À l'inverse, un article ajouté ailleurs qui
contredit frontalement une réponse ne touche aucun passage cité et passait
inaperçu. Les deux erreurs ont la même cause : personne ne lisait la réponse.

Le pipeline est un entonnoir, du gratuit au coûteux, et **seul le dernier étage
prononce un verdict** :

::

    unités de changement   (diff aligné, gratuit — services/obsolescence.py)
            ↓
    candidates             (citantes du document + voisines du domaine, dense Qdrant)
            ↓
    unites_pertinentes     (reranker : quelles unités portent sur cette question ?)
            ↓
    juger                  (LLM : ce changement contredit-il cette réponse ?)
            ↓
    decider                (retrait sec / relecture / rien)

Chaque étage est **orienté rappel** : un faux positif coûte un appel au modèle,
un faux négatif laisse servir une réponse fausse en silence. Les seuils sont donc
bas et les pannes se replient toujours vers « fais lire un humain », jamais vers
« laisse passer » ni vers « détruis ».

Étages 1 et 2+3 extraits dans :
  - reverification_candidates.py (collecte des candidates)
  - reverification_scoring.py (reranker + LLM)
"""

from app.models.reponse import Reponse
from app.services.obsolescence import (
    RAISON_CONTREDITE,
    RAISON_CONTREDITE_PROB,
    RAISON_MODIF,
    fermeture_copies,
    lever_a_relire,
    poser_a_relire,
    retirer_du_service,
    serialiser_unites,
)
from app.services.reverification_candidates import (  # noqa: F401
    Candidate,
    rassembler_candidates,
)
from app.services.reverification_scoring import (  # noqa: F401
    MAX_UNITES_PAR_REPONSE,
    SEUIL_RERANK,
    VERDICT_CONTREDITE,
    VERDICT_INCERTAIN,
    VERDICT_INTACTE,
    VERDICTS,
    juger,
    unites_pertinentes,
)
from sqlalchemy.orm import Session

__all__ = [
    # constants
    "MAX_UNITES",
    "MAX_JUGEMENTS",
    "MAX_UNITES_PAR_REPONSE",
    "SEUIL_RERANK",
    "VERDICT_CONTREDITE",
    "VERDICT_INTACTE",
    "VERDICT_INCERTAIN",
    "VERDICTS",
    "ACTION_RETIREE",
    "ACTION_A_RELIRE",
    "ACTION_INTACTE",
    # types
    "Candidate",
    # functions
    "rassembler_candidates",
    "unites_pertinentes",
    "juger",
    "decider",
    "signaler_sans_juger",
    "tracer",
]

# Au-delà, le document n'a pas été modifié : il a été réécrit. Il n'y a plus rien
# à discriminer — juger 200 réponses contre 300 changements coûterait une fortune
# pour conclure « tout est suspect », ce qu'on sait déjà. Le worker bascule alors
# sur le signalement en bloc, sans un seul appel au modèle.
MAX_UNITES = 40

# Budget d'appels au LLM par mise à jour. Le surplus n'est jamais ignoré : il part
# en relecture humaine avec sa propre raison, pour que la troncature soit visible.
MAX_JUGEMENTS = 25

ACTION_RETIREE = "retiree"
ACTION_A_RELIRE = "a_relire"
ACTION_INTACTE = "intacte"


def decider(
    db: Session,
    candidate: Candidate,
    verdict: str,
    justification: str,
    unites: list,
    doc_id: str,
    version: int,
) -> str:
    """Applique le verdict, et renvoie l'action retenue pour le comptage.

    Une seule asymétrie, mais elle est le garde-fou central : **une réponse qui
    ne cite pas le document ne peut pas être retirée automatiquement.** Elle n'a
    été rapprochée du changement que par similarité vectorielle entre un
    paragraphe et une question — deux objets de nature différente, indexés pour
    autre chose. Détruire à tort une canonique à douze validations coûte bien plus
    cher que d'imposer vingt relectures ; le verdict plafonne donc à la relecture.

    Chaque décision est commitée séparément (``retirer_du_service`` commite) : un
    worker qui meurt à mi-parcours conserve les jugements déjà payés, et le rejeu
    ne repasse que sur le reliquat.
    """
    famille = _famille(db, candidate.reponse)
    extraits = serialiser_unites(unites)["unites"]

    if verdict == VERDICT_CONTREDITE and candidate.citante:
        retirer_du_service(db, famille, RAISON_CONTREDITE, doc_id, version)
        tracer(db, famille, justification, extraits)
        return ACTION_RETIREE

    if verdict == VERDICT_CONTREDITE:
        poser_a_relire(famille, RAISON_CONTREDITE_PROB, doc_id, version)
        tracer(db, famille, justification, extraits)
        return ACTION_A_RELIRE

    if verdict == VERDICT_INTACTE:
        for r in famille:
            # Ne jamais effacer le signalement d'un *autre* document : cette
            # réponse peut attendre une relecture déclenchée ailleurs, que ce
            # job n'a pas instruite et n'a aucun titre à clore.
            if r.a_relire_doc_id == doc_id:
                lever_a_relire(r)
                r.analyse_justification = None
                r.analyse_extraits = None
        db.commit()
        return ACTION_INTACTE

    poser_a_relire(famille, RAISON_MODIF, doc_id, version)
    tracer(db, famille, justification, extraits)
    return ACTION_A_RELIRE


def signaler_sans_juger(
    db: Session,
    candidates: list[Candidate],
    raison: str,
    justification: str,
    doc_id: str,
    version: int,
) -> int:
    """Envoie en relecture des réponses qu'on n'a pas pu juger, et le dit.

    Sert les trois cas où le pipeline s'arrête avant le verdict : budget d'appels
    épuisé, document réécrit au-delà du plafond, Albert injoignable. Aucun de ces
    cas ne doit être silencieux — c'est précisément parce que l'ancien système
    tronquait sans le dire qu'on ne pouvait pas lui faire confiance.
    """
    for candidate in candidates:
        famille = _famille(db, candidate.reponse)
        poser_a_relire(famille, raison, doc_id, version)
        tracer(db, famille, justification, None)
    db.commit()
    return len(candidates)


def _famille(db: Session, reponse: Reponse) -> list[Reponse]:
    """La réponse et toutes ses copies encore en service.

    Les copies SUGGESTION/CANONIQUE ne citent aucun chunk : elles ne se rattachent
    à leur origine que par ``reponse_source_id``. Décider sur la seule graine
    laisserait la copie indexée, donc resservie.
    """
    return db.query(Reponse).filter(Reponse.id.in_(fermeture_copies(db, {reponse.id}))).all()


def tracer(db: Session, reponses: list[Reponse], justification: str, extraits: list[dict] | None) -> None:
    for r in reponses:
        r.analyse_justification = justification or None
        r.analyse_extraits = {"unites": extraits} if extraits else None
    db.commit()
