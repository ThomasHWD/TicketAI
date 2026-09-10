"""Accès base de données pour le pipeline de questions."""

import uuid

from sqlalchemy.orm import Session

from app.models.reponse import Reponse
from app.models.ticket import Ticket


class TicketDisparu(Exception):
    """Le ticket ciblé n'existe plus en base : le job n'a plus d'objet.

    Ce n'est pas une panne, c'est une course perdue — une suppression, ou un
    retraitement enfilé sur un ticket effacé depuis. La distinguer d'une erreur
    ordinaire est indispensable : réessayer ne peut rien y changer, et chaque
    tentative repaie l'embedding, le rerank et la génération pour rien.
    """


def upsert_ticket(db: Session, job_id: uuid.UUID, ticket_id: uuid.UUID | None = None, **fields) -> Ticket:
    if ticket_id is not None:
        ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
        if ticket is None:
            raise TicketDisparu(str(ticket_id))
        for key in ("question", "domaine", "user_id", "objet"):
            fields.pop(key, None)
        for key, value in fields.items():
            setattr(ticket, key, value)
        db.flush()
        return ticket

    ticket = db.query(Ticket).filter(Ticket.job_id == job_id).first()
    if ticket is None:
        ticket = Ticket(id=uuid.uuid4(), job_id=job_id, **fields)
        db.add(ticket)
    else:
        for key, value in fields.items():
            setattr(ticket, key, value)
    db.flush()
    return ticket


def upsert_reponse(
    db: Session,
    ticket: Ticket,
    contenu: str,
    top_score: float,
    source: str = "LLM",
    reponse_source_id: uuid.UUID | None = None,
    statut: str = "EN_ATTENTE",
    canonique: bool = False,
    question_suivi: str | None = None,
    nouveau: bool = False,
    tag: str | None = None,
) -> Reponse:
    reponse = (
        None
        if nouveau
        else (db.query(Reponse).filter(Reponse.ticket_id == ticket.id, Reponse.obsolete.is_(False)).first())
    )
    if reponse is None:
        reponse = Reponse(
            id=uuid.uuid4(),
            ticket_id=ticket.id,
            contenu=contenu,
            statut=statut,
            source=source,
            score_similarite=top_score,
            reponse_source_id=reponse_source_id,
            canonique=canonique,
            question_suivi=question_suivi,
            tag=tag,
        )
        db.add(reponse)
    else:
        reponse.contenu = contenu
        reponse.score_similarite = top_score
    db.flush()
    return reponse
