"""Calcul de l'impact d'une mise à jour documentaire sur les réponses validées."""

from app.models.reponse import Reponse
from app.models.reponse_chunk import ReponseChunk
from app.models.ticket import Ticket
from app.services.obsolescence import MAX_EXTRAITS, extrait
from sqlalchemy.orm import Session


def item_impact(db: Session, reponse: Reponse, doc_id: str, indices: set[int], anciens: dict[int, str]) -> dict:
    """Ligne de l'écran d'impact : la réponse, et les passages qui la fondaient."""
    cites = {
        r[0]
        for r in db.query(ReponseChunk.chunk_index)
        .filter(ReponseChunk.reponse_id == reponse.id, ReponseChunk.doc_id == doc_id)
        .all()
    }
    modifies = sorted(cites & indices)
    ticket = db.query(Ticket).filter(Ticket.id == reponse.ticket_id).first()
    return {
        "reponse_id": str(reponse.id),
        "question": reponse.question_suivi or (ticket.question if ticket else ""),
        "canonique": reponse.canonique,
        "nb_validations": reponse.nb_validations,
        "chunks_modifies": modifies,
        "extraits": [extrait(anciens.get(i, "")) for i in modifies[:MAX_EXTRAITS]],
    }


def items_a_analyser(db: Session, reponses: list) -> list[dict]:
    """Cartes des réponses qui seront jugées, pour l'écran d'impact."""
    tickets = {t.id: t for t in db.query(Ticket).filter(Ticket.id.in_([r.ticket_id for r in reponses])).all()}
    return [
        {
            "reponse_id": str(r.id),
            "ticket_id": str(r.ticket_id),
            "question": r.question_suivi or (tickets[r.ticket_id].question if r.ticket_id in tickets else ""),
            "contenu": r.contenu_corrige or r.contenu or "",
            "canonique": r.canonique,
            "nb_validations": r.nb_validations,
        }
        for r in reponses
    ]
