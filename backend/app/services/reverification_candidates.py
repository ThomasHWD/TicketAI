"""Étage 1 du pipeline de révérification : collecte des réponses candidates.

Deux sources : les réponses qui citent le document modifié (citantes) et celles
dont la question ressemble à un changement (voisines). Voir reverification.py
pour la description complète du pipeline.
"""

import uuid
from dataclasses import dataclass

from app.models.reponse import Reponse
from app.models.ticket import Ticket
from app.services.embedding import embed_texts
from app.services.obsolescence import (
    Unite,
    fermeture_copies,
    racines,
    reponses_obsoletes,
)
from app.services.qdrant import COLLECTION_NAME, client
from qdrant_client.models import (
    FieldCondition,
    Filter,
    IsEmptyCondition,
    MatchValue,
    PayloadField,
)
from sqlalchemy.orm import Session

# Réponses ramenées par unité de changement lors du rappel vectoriel.
TOP_K_UNITE = 20

# Seuil du rappel dense. Délibérément bas : l'embedding ne décide de rien, il
# élargit. Le reranker filtre derrière, et le modèle tranche.
SEUIL_RAPPEL = 0.35


@dataclass
class Candidate:
    """Une réponse à juger, et ce qu'on sait déjà d'elle avant de la juger."""

    reponse: Reponse
    question: str
    # Cite au moins un chunk du document modifié. Conditionne la sévérité maximale
    # atteignable : voir `decider`.
    citante: bool
    # Cite un chunk qui a *disparu* de la nouvelle version. Signal factuel, pas
    # statistique : il court-circuite le filtre de pertinence.
    prioritaire: bool = False

    @property
    def texte(self) -> str:
        return self.reponse.contenu_corrige or self.reponse.contenu or ""

    def _cle_tri(self) -> tuple:
        return (self.prioritaire, self.citante, self.reponse.canonique, self.reponse.nb_validations or 0)


def rassembler_candidates(
    db: Session,
    doc_id: str,
    domaine: str,
    unites: list[Unite],
    indices_disparus: set[int],
) -> list[Candidate]:
    """Les réponses susceptibles d'être touchées, les plus exposées d'abord.

    Deux sources, et il faut les deux :

    * **les citantes** — toutes les VALIDÉE encore servies qui s'appuient sur ce
      document. Le périmètre est le document entier et non « près de la zone
      modifiée » : la contradiction est par définition ailleurs dans le cas qu'on
      cherche à rattraper.
    * **les voisines du domaine** — celles dont la question ressemble à un
      changement, retrouvées en interrogeant Qdrant avec le texte de l'unité.
      Elles couvrent le cas où le nouvel article d'une charte contredit une
      réponse bâtie sur un *autre* document.

    Le tri n'est pas cosmétique : c'est l'ordre dans lequel le budget d'appels au
    modèle sera dépensé. Les prioritaires d'abord, puis les canoniques, puis les
    plus validées — c'est-à-dire les plus resservies, donc celles dont l'erreur
    se propage le plus.

    La liste est réduite à ses ``racines`` : les deux sources remontent les copies
    SUGGESTION/CANONIQUE, et une réponse réutilisée cinq fois coûterait sinon cinq
    jugements identiques. ``decider`` rouvre la famille au moment d'appliquer.
    """
    citantes = reponses_obsoletes(db, doc_id, indices=None)
    ids_citantes = {r.id for r in citantes}

    ids_prioritaires: set[uuid.UUID] = set()
    if indices_disparus:
        ids_prioritaires = {r.id for r in reponses_obsoletes(db, doc_id, indices=indices_disparus)}

    voisines = [r for r in _voisines(db, domaine, unites) if r.id not in ids_citantes]

    distinctes = racines(citantes + voisines)
    questions = _questions(db, distinctes)
    candidates = [
        Candidate(
            reponse=r,
            question=questions.get(r.id, ""),
            citante=r.id in ids_citantes,
            prioritaire=r.id in ids_prioritaires,
        )
        for r in distinctes
    ]

    candidates.sort(key=Candidate._cle_tri, reverse=True)
    return candidates


def _voisines(db: Session, domaine: str, unites: list[Unite]) -> list[Reponse]:
    """Réponses validées du domaine dont la question ressemble à un changement.

    Une requête **dense uniquement** : ``embed_texts`` renvoie un vecteur sparse
    vide (``{"indices": [], "values": []}``), interroger la branche sparse
    reviendrait à envoyer un vecteur nul à Qdrant. Pour la même raison on
    n'emprunte pas ``search_hybrid``, qui ne sait pas non plus cibler les points
    de réponse.

    ``must_not=[IsEmpty("reponse_id")]`` est le seul moyen d'isoler ces points :
    ``feedback_job`` les écrit avec
    ``{reponse_id, ticket_id, contenu, domaine, question_indexee}`` et **sans**
    ``doc_id``, dans la même collection que les chunks de document.
    Aucun index de payload sur ``reponse_id`` — Qdrant filtre donc en scan, ce qui
    reste acceptable à cette volumétrie et se paye une fois par mise à jour.

    Une réponse porte un point par formulation humainement validée : le scroll peut
    donc la remonter plusieurs fois, sous des ``question_indexee`` différentes. D'où
    le ``set`` de ``reponse_id`` — c'est la réponse qu'on juge, pas la formulation.

    Une panne d'embedding ou de Qdrant rend une liste vide et n'interrompt rien :
    les citantes, elles, sont connues sans appel réseau et restent jugées.
    """
    if not unites:
        return []

    try:
        embeddings = embed_texts([u.texte for u in unites], is_query=True)
    except Exception as exc:
        print(f"[REVERIF] embedding des changements indisponible ({exc}) — rappel limité aux citantes")
        return []

    filtre = Filter(
        must=[FieldCondition(key="domaine", match=MatchValue(value=domaine))],
        must_not=[IsEmptyCondition(is_empty=PayloadField(key="reponse_id"))],
    )

    trouves: set[uuid.UUID] = set()
    for emb in embeddings:
        try:
            res = client.query_points(
                collection_name=COLLECTION_NAME,
                query=emb["dense"],
                using="dense",
                query_filter=filtre,
                limit=TOP_K_UNITE,
                with_payload=["reponse_id"],
            )
        except Exception as exc:
            print(f"[REVERIF] rappel Qdrant impossible ({exc})")
            return []
        for point in res.points:
            if point.score < SEUIL_RAPPEL:
                continue
            brut = (point.payload or {}).get("reponse_id")
            if brut:
                try:
                    trouves.add(uuid.UUID(str(brut)))
                except ValueError:
                    continue

    if not trouves:
        return []

    # Une copie SUGGESTION/CANONIQUE ne porte pas de point à elle : c'est la source
    # qui a été retrouvée. La descente transitive ramène la famille, faute de quoi
    # on retirerait la graine et la copie continuerait d'être servie.
    return (
        db.query(Reponse)
        .filter(
            Reponse.id.in_(fermeture_copies(db, trouves)),
            Reponse.statut == "VALIDÉE",
            Reponse.obsolete.is_(False),
        )
        .all()
    )


def _questions(db: Session, reponses: list[Reponse]) -> dict[uuid.UUID, str]:
    """La question à laquelle chaque réponse répond — la précision si elle existe.

    ``question_suivi`` prime sur la question du ticket pour la même raison qu'à
    l'indexation (cf. ``feedback_job``) : quand une réponse est née d'une relance,
    c'est la relance qui la décrit, pas la demande initiale du fil.
    """
    ids = {r.ticket_id for r in reponses if r.ticket_id is not None}
    tickets = {t.id: t.question for t in db.query(Ticket).filter(Ticket.id.in_(ids)).all()} if ids else {}
    return {r.id: r.question_suivi or tickets.get(r.ticket_id, "") for r in reponses}
