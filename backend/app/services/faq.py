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
from app.services.search import rechercher_points_reponses
from sqlalchemy.orm import Session

# Une réponse porte un point Qdrant **par formulation validée**
# (`feedback_job(..., formulation_id=...)`), et les non-canoniques seront écartées
# par la requête SQL. On sur-échantillonne donc pour ne pas rendre moins de
# résultats que demandé.
FACTEUR_SUR_ECHANTILLONNAGE = 4

# Un repli reste un repli : au-delà de trois pistes, la page ne propose plus, elle noie.
MAX_INCERTAINS = 3


def _meilleurs_points(chunks: list[dict], seuil: float) -> dict[str, tuple[float, str | None]]:
    """Agrège les points par `reponse_id` : `{reponse_id: (meilleur_score, question_indexee)}`.

    La question retenue est celle du point **qui a obtenu le meilleur score**, pas
    celle du ticket d'origine : c'est la formulation que l'utilisateur a réellement
    matchée, donc la seule qu'il ait du sens de lui afficher.
    """
    meilleurs: dict[str, tuple[float, str | None]] = {}
    for chunk in chunks:
        reponse_id = chunk.get("reponse_id")
        score = chunk.get("score_cosinus", 0.0)
        if not reponse_id or score < seuil:
            continue
        cle = str(reponse_id)
        if score > meilleurs.get(cle, (-1.0, None))[0]:
            meilleurs[cle] = (score, chunk.get("question_indexee"))
    return meilleurs


def rechercher_faq(db: Session, question: str, limite: int) -> dict[str, list[dict]]:
    """Réponses canoniques proches de `question`, tous domaines confondus.

    Renvoie deux rangs :

    - `resultats` — ce qui franchit `faq_seuil_pertinence`, au plus `limite` ;
    - `incertains` — **uniquement si `resultats` est vide**, ce qui atteint au
      moins `faq_seuil_incertain`. C'est une piste, pas une réponse : la bande
      sous le seuil mélange bonnes et mauvaises correspondances sans qu'aucune
      valeur ne les sépare. Le cantonnement au cas « rien trouvé » est une règle
      métier, pas un choix d'affichage : proposer de l'incertain à côté d'une
      réponse sûre ne ferait que la diluer.
    """
    chunks = rechercher_points_reponses(question, top_k=limite * FACTEUR_SUR_ECHANTILLONNAGE)

    meilleurs = _meilleurs_points(chunks, settings.faq_seuil_incertain)
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
        )
        .all()
    )

    certains: list[tuple[float, dict]] = []
    incertains: list[tuple[float, dict]] = []
    for reponse, ticket in resultats:
        score, question_indexee = meilleurs[str(reponse.id)]
        rang = certains if score >= settings.faq_seuil_pertinence else incertains
        rang.append(
            (
                score,
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

    # Le score ordonne, mais ne sort pas de l'API : un cosinus brut n'a aucun sens
    # pour un utilisateur et invite à des interprétations fausses.
    def ordonner(rang: list[tuple[float, dict]], maximum: int) -> list[dict]:
        rang.sort(key=lambda paire: paire[0], reverse=True)
        return [item for _, item in rang[:maximum]]

    servis = ordonner(certains, limite)
    return {
        "resultats": servis,
        "incertains": [] if servis else ordonner(incertains, MAX_INCERTAINS),
    }
