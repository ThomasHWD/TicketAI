import asyncio

from fastapi import APIRouter, HTTPException
from sqlalchemy import exists

from app.core.permissions import check_domain_write
from app.core.security import BackofficeUser
from app.database import SessionLocal
from app.models.groupe import Groupe
from app.models.groupe import user_groups as ug_table
from app.models.reponse import Reponse
from app.models.reponse_chunk import ReponseChunk
from app.models.ticket import Ticket
from app.models.ticket_event import TicketEvent
from app.models.user import User
from app.schemas.ticket import AssignerRequest, RecheminerRequest
from app.services.broadcast import broadcast_async
from app.services.ticket_service import full_name, parse_ticket_id, serialize_ticket
from app.workers.question import question_job

router = APIRouter()


@router.post("/tickets/{ticket_id}/recheminer")
async def recheminer_ticket(ticket_id: str, payload: RecheminerRequest, current_user: BackofficeUser):
    """Réachemine un ticket vers un autre domaine et relance le pipeline RAG sur le bon domaine."""
    tid = parse_ticket_id(ticket_id)
    db = SessionLocal()
    try:
        ticket = db.query(Ticket).filter(Ticket.id == tid).first()
        if not ticket:
            raise HTTPException(404, "Ticket introuvable")
        check_domain_write(ticket.domaine, current_user)
        if ticket.statut_ticket != "RÉPONDU":
            raise HTTPException(422, "Seuls les tickets en statut RÉPONDU peuvent être réacheminés")
        nouveau_domaine = payload.nouveau_domaine.strip().upper()
        domaine_existe = db.query(exists().where(Groupe.domaine == nouveau_domaine)).scalar()
        if not domaine_existe:
            raise HTTPException(422, f"Le domaine {nouveau_domaine} n'existe pas")
        if nouveau_domaine == ticket.domaine:
            raise HTTPException(422, "Le nouveau domaine est identique au domaine actuel")

        old_domaine = ticket.domaine
        user_id = ticket.user_id
        question = ticket.question

        has_suivi = (
            db.query(Reponse)
            .filter(Reponse.ticket_id == tid, Reponse.question_suivi.isnot(None))
            .first()
        )
        if has_suivi:
            raise HTTPException(422, "Un ticket ayant reçu des précisions ne peut pas être réacheminé")

        reponse_en_attente = (
            db.query(Reponse)
            .filter(Reponse.ticket_id == tid, Reponse.statut == "EN_ATTENTE")
            .first()
        )
        if reponse_en_attente:
            db.query(ReponseChunk).filter(ReponseChunk.reponse_id == reponse_en_attente.id).delete()
            db.delete(reponse_en_attente)

        ticket.reroute_source_domaine = old_domaine
        ticket.domaine = nouveau_domaine
        ticket.statut_ticket = "NOUVEAU"
        ticket.statut_job = "EN_ATTENTE"
        ticket.closed_at = None
        ticket.assigned_to = None
        ticket.locked_by = None
        ticket.locked_at = None
        ticket.lock_expires_at = None

        db.add(
            TicketEvent(
                ticket_id=tid,
                type="RECHEMINE",
                actor_id=current_user.id,
                actor_email=current_user.email,
                actor_nom_complet=full_name(current_user),
                meta={"from": old_domaine, "to": nouveau_domaine, "raison": payload.raison},
            )
        )
        db.commit()
        result = serialize_ticket(ticket)
    finally:
        db.close()

    question_job.apply_async(
        args=[question, nouveau_domaine, str(user_id) if user_id else None],
        kwargs={"ticket_id": ticket_id, "retraiter": True},
        queue="queue_questions",
    )

    broadcasts = [
        broadcast_async(
            f"sse:domain:{old_domaine}", "ticket_rerouted",
            {"ticket_id": ticket_id, "new_domaine": nouveau_domaine},
        ),
        broadcast_async(
            f"sse:domain:{nouveau_domaine}", "ticket_rerouted",
            {"ticket_id": ticket_id, "from_domaine": old_domaine},
        ),
    ]
    if user_id:
        broadcasts.append(broadcast_async(f"sse:user:{user_id}", "ticket_rerouted", {"ticket_id": ticket_id}))
    await asyncio.gather(*broadcasts)
    return result


@router.post("/tickets/{ticket_id}/assigner")
async def assigner_ticket(ticket_id: str, payload: AssignerRequest, current_user: BackofficeUser):
    """Assigne le ticket à un validateur du même domaine."""
    tid = parse_ticket_id(ticket_id)
    db = SessionLocal()
    try:
        ticket = db.query(Ticket).filter(Ticket.id == tid).first()
        if not ticket:
            raise HTTPException(404, "Ticket introuvable")
        check_domain_write(ticket.domaine, current_user)
        is_member = db.query(
            exists()
            .where(Groupe.domaine == ticket.domaine)
            .where(ug_table.c.groupe_id == Groupe.id)
            .where(ug_table.c.user_id == payload.assignee_id)
        ).scalar()
        if not is_member:
            raise HTTPException(422, "L'assigné n'appartient pas au domaine du ticket")
        domaine = ticket.domaine
        ticket.assigned_to = payload.assignee_id
        ticket.locked_by = None
        ticket.locked_at = None
        ticket.lock_expires_at = None
        assignee = db.query(User).filter(User.id == payload.assignee_id).first()
        db.add(
            TicketEvent(
                ticket_id=tid,
                type="ASSIGNE",
                actor_id=current_user.id,
                actor_email=current_user.email,
                actor_nom_complet=full_name(current_user),
                meta={
                    "assignee_id": str(payload.assignee_id),
                    "assignee_email": assignee.email if assignee else None,
                    "assignee_nom": full_name(assignee) if assignee else None,
                },
            )
        )
        db.commit()
        result = serialize_ticket(ticket)
    finally:
        db.close()
    await asyncio.gather(
        broadcast_async(f"sse:domain:{domaine}", "ticket_unlocked", {"ticket_id": ticket_id}),
        broadcast_async(f"sse:domain:{domaine}", "ticket_assigned", {"ticket_id": ticket_id, "domaine": domaine}),
        broadcast_async(
            f"sse:user:{payload.assignee_id}", "ticket_assigned", {"ticket_id": ticket_id, "domaine": domaine}
        ),
    )
    return result


@router.post("/tickets/{ticket_id}/desassigner")
async def desassigner_ticket(ticket_id: str, current_user: BackofficeUser):
    """Remet le ticket dans le pot commun (supprime l'assignation)."""
    tid = parse_ticket_id(ticket_id)
    db = SessionLocal()
    try:
        ticket = db.query(Ticket).filter(Ticket.id == tid).first()
        if not ticket:
            raise HTTPException(404, "Ticket introuvable")
        check_domain_write(ticket.domaine, current_user)
        domaine = ticket.domaine
        ticket.assigned_to = None
        db.add(
            TicketEvent(
                ticket_id=tid,
                type="DESASSIGNE",
                actor_id=current_user.id,
                actor_email=current_user.email,
                actor_nom_complet=full_name(current_user),
                meta={},
            )
        )
        db.commit()
        result = serialize_ticket(ticket)
    finally:
        db.close()
    await broadcast_async(f"sse:domain:{domaine}", "ticket_unassigned", {"ticket_id": ticket_id, "domaine": domaine})
    return result
