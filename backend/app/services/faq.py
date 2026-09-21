"""FAQ: semantic search over canonical responses, read-only. No ticket created, no generation, no guard — shows what"""

import uuid

from app.config import settings
from app.models.reponse import Reponse
from app.models.ticket import Ticket
from app.services.search import franchit_le_rappel, rechercher_points_reponses
from sqlalchemy.orm import Session

# A response has one Qdrant point per validated formulation; non-canonicals are filtered out by SQL. Over-sample so we
FACTEUR_SUR_ECHANTILLONNAGE = 4

# Beyond three hints the page stops proposing and starts drowning.
MAX_INCERTAINS = 3


def _meilleurs_points(chunks: list[dict]) -> dict[str, dict]:
    """Best point per reponse_id by RRF rank. Displayed question is the indexed formulation the user actually"""
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
    """Two tiers — resultats when cosine is confident, incertains (hint only) when not; lexical-only candidates land"""
    chunks = rechercher_points_reponses(question, top_k=limite * FACTEUR_SUR_ECHANTILLONNAGE)

    meilleurs = _meilleurs_points(chunks)
    if not meilleurs:
        return {"resultats": [], "incertains": []}

    # SQL mirror of peut_servir_sans_revue; a_relire filtered — this page has no reviewer, showing it would serve it
    resultats = (
        db.query(Reponse, Ticket)
        .join(Ticket, Ticket.id == Reponse.ticket_id)
        .filter(
            Reponse.id.in_([uuid.UUID(r) for r in meilleurs]),
            Reponse.canonique.is_(True),
            Reponse.a_relire.is_(False),
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
        # cosine only opens resultats — without a judge, word overlap alone is only a hint.
        sur = point.get("score_cosinus", 0.0) >= settings.faq_seuil_pertinence
        rang = certains if sur else incertains
        rang.append(
            (
                point.get("score_rrf", 0.0),
                {
                    "reponse_id": str(reponse.id),
                    # fallback for points written before multi-formulation indexing.
                    "question": question_indexee or reponse.question_suivi or ticket.question,
                    "domaine": ticket.domaine,
                    "contenu": reponse.contenu_corrige or reponse.contenu,
                    "tag": reponse.tag,
                    "nb_validations": reponse.nb_validations,
                    "validated_at": reponse.validated_at.isoformat() if reponse.validated_at else None,
                },
            )
        )

    # scores order results but never leave the API — meaningless to users.
    def ordonner(rang: list[tuple[float, dict]], maximum: int) -> list[dict]:
        rang.sort(key=lambda paire: paire[0], reverse=True)
        return [item for _, item in rang[:maximum]]

    servis = ordonner(certains, limite)
    return {
        "resultats": servis,
        "incertains": [] if servis else ordonner(incertains, MAX_INCERTAINS),
    }
