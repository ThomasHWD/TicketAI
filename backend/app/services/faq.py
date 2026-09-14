"""FAQ : recherche sémantique dans les réponses canoniques.

Consultation pure. Aucun ticket n'est créé, aucune génération LLM n'a lieu, le
garde canonique n'est pas appelé : on ne *sert* rien sans revue humaine, on
*montre* ce qu'un humain a déjà validé au moins `SEUIL_CANONIQUE` fois.

Coût d'une recherche : un unique appel d'embedding Albert, suivi d'une seule
interrogation vectorielle tous domaines confondus.
"""

import uuid

from app.config import settings
from app.models.reponse import Reponse
from app.models.ticket import Ticket
from app.services.search import franchit_le_rappel, rechercher_points_reponses
from sqlalchemy.orm import Session

# Une réponse porte un point Qdrant **par formulation validée**
# (`feedback_job(..., formulation_id=...)`), et les non-canoniques seront écartées
# par la requête SQL. On sur-échantillonne donc pour ne pas rendre moins de
# résultats que demandé.
FACTEUR_SUR_ECHANTILLONNAGE = 4

# Un repli reste un repli : au-delà de trois pistes, la page ne propose plus, elle noie.
MAX_INCERTAINS = 3


def _meilleurs_points(chunks: list[dict]) -> dict[str, dict]:
    """Le meilleur point par `reponse_id`, retenu au **rang RRF**.

    La question affichée sera celle de ce point, pas celle du ticket d'origine :
    c'est la formulation que l'utilisateur a réellement matchée.

    Le tri est le rôle de la fusion ; la sélection, elle, se fait par disjonction
    sur les signaux bruts (`franchit_le_rappel`) — un point retenu par les seuls
    mots doit pouvoir entrer, c'est tout l'intérêt de BM25.
    """
    meilleurs: dict[str, dict] = {}
    for chunk in chunks:
        reponse_id = chunk.get("reponse_id")
        if not reponse_id or not franchit_le_rappel(chunk, settings.faq_seuil_incertain):
            continue
        cle = str(reponse_id)
        if chunk.get("score_rrf", 0.0) > meilleurs.get(cle, {}).get("score_rrf", -1.0):
            meilleurs[cle] = chunk
    return meilleurs


def rechercher_faq(db: Session, question: str, limite: int) -> dict[str, list[dict]]:
    """Réponses canoniques proches de `question`, tous domaines confondus.

    Renvoie deux rangs :

    - `resultats` — ce dont le **cosinus** franchit `faq_seuil_pertinence` ;
    - `incertains` — **uniquement si `resultats` est vide** : ce qui atteint
      `faq_seuil_incertain`, ou ce qui n'est passé que par la **porte lexicale**.

    Un candidat retenu par les seuls mots va donc en piste, jamais en réponse. La
    raison tient en une phrase : ailleurs dans le système, un tel candidat est
    soumis au juge, qui tranche ; ici il n'y a pas de juge, donc rien ne vient
    confirmer qu'un recouvrement de mots vaut une réponse. On le propose sans
    l'affirmer.

    Le cantonnement des pistes au cas « rien trouvé » est une règle métier, pas un
    choix d'affichage : proposer de l'incertain à côté d'une réponse sûre ne
    ferait que la diluer.
    """
    chunks = rechercher_points_reponses(question, top_k=limite * FACTEUR_SUR_ECHANTILLONNAGE)

    meilleurs = _meilleurs_points(chunks)
    if not meilleurs:
        return {"resultats": [], "incertains": []}

    # Mêmes prédicats que GET /reponses/canoniques (api/v1/reponses/listing.py).
    # `a_relire` n'est volontairement pas filtré : le pipeline continue de servir
    # ces réponses, la FAQ doit dire la même chose que lui.
    resultats = (
        db.query(Reponse, Ticket)
        .join(Ticket, Ticket.id == Reponse.ticket_id)
        .filter(
            Reponse.id.in_([uuid.UUID(r) for r in meilleurs]),
            Reponse.canonique.is_(True),
            Reponse.obsolete.is_(False),
            Reponse.faq_visible.is_(True),
        )
        .all()
    )

    certains: list[tuple[float, dict]] = []
    incertains: list[tuple[float, dict]] = []
    for reponse, ticket in resultats:
        point = meilleurs[str(reponse.id)]
        question_indexee = point.get("question_indexee")
        # Seul le **cosinus** ouvre le rang des réponses : sans juge pour le
        # confirmer, un simple recouvrement de mots ne fait qu'une piste.
        sur = point.get("score_cosinus", 0.0) >= settings.faq_seuil_pertinence
        rang = certains if sur else incertains
        rang.append(
            (
                point.get("score_rrf", 0.0),
                {
                    "reponse_id": str(reponse.id),
                    # Repli pour les points écrits avant l'indexation multi-formulations.
                    "question": question_indexee or reponse.question_suivi or ticket.question,
                    "domaine": ticket.domaine,
                    "contenu": reponse.contenu_corrige or reponse.contenu,
                    "tag": reponse.tag,
                    "nb_validations": reponse.nb_validations,
                    "validated_at": reponse.validated_at.isoformat() if reponse.validated_at else None,
                },
            )
        )

    # Le rang RRF ordonne — c'est son rôle — mais aucun score ne sort de l'API :
    # ils n'ont aucun sens pour un utilisateur et invitent à des lectures fausses.
    def ordonner(rang: list[tuple[float, dict]], maximum: int) -> list[dict]:
        rang.sort(key=lambda paire: paire[0], reverse=True)
        return [item for _, item in rang[:maximum]]

    servis = ordonner(certains, limite)
    return {
        "resultats": servis,
        "incertains": [] if servis else ordonner(incertains, MAX_INCERTAINS),
    }
