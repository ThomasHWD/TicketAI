import uuid
from datetime import datetime, timedelta, timezone

from celery.result import AsyncResult
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import or_

from app.config import settings
from app.database import SessionLocal
from app.models.ticket import Ticket
from app.workers.celery_app import celery_app
from app.workers.question import question_job

router = APIRouter()

DOMAINES_VALIDES = {"IT", "RH", "JURIDIQUE"}


class QuestionRequest(BaseModel):
    question: str
    domaine: str
    user_id: str | None = None


class SuiviRequest(BaseModel):
    question: str
    user_id: str | None = None


class CloturerRequest(BaseModel):
    user_id: str | None = None


class LockRequest(BaseModel):
    validator_id: uuid.UUID


def lock_info(ticket: Ticket, now: datetime | None = None) -> dict:
    """Sérialise l'état du verrou. Un bail expiré est considéré comme libre."""
    now = now or datetime.now(timezone.utc)
    actif = bool(
        ticket.locked_by
        and ticket.lock_expires_at
        and ticket.lock_expires_at > now
    )
    return {
        "locked_by": str(ticket.locked_by) if actif else None,
        "locked_by_email": ticket.locker.email if actif and ticket.locker else None,
        "lock_expires_at": ticket.lock_expires_at.isoformat() if actif else None,
    }


def _serialize_ticket(ticket: Ticket) -> dict:
    return {
        "id": str(ticket.id),
        "question": ticket.question,
        "domaine": ticket.domaine,
        "statut_ticket": ticket.statut_ticket,
        "statut_job": ticket.statut_job,
        "user_id": str(ticket.user_id) if ticket.user_id else None,
        "user_email": ticket.user.email if ticket.user else None,
        "canonique": ticket.canonique,
        "created_at": ticket.created_at.isoformat() if ticket.created_at else None,
        "closed_at": ticket.closed_at.isoformat() if ticket.closed_at else None,
        **lock_info(ticket),
    }


def _acquire_lock(db, tid: uuid.UUID, validator_id: uuid.UUID) -> Ticket | None:
    """Acquiert/prolonge le bail de façon atomique (UPDATE conditionnel).

    Réussit uniquement si le ticket est libre, déjà détenu par ce validateur,
    ou si le bail précédent a expiré. Renvoie le ticket si acquis, sinon None.
    """
    now = datetime.now(timezone.utc)
    expiry = now + timedelta(seconds=settings.lock_ttl_seconds)
    rows = (
        db.query(Ticket)
        .filter(
            Ticket.id == tid,
            or_(
                Ticket.locked_by.is_(None),
                Ticket.locked_by == validator_id,
                Ticket.lock_expires_at < now,
            ),
        )
        .update(
            {
                Ticket.locked_by: validator_id,
                Ticket.locked_at: now,
                Ticket.lock_expires_at: expiry,
            },
            synchronize_session=False,
        )
    )
    db.commit()
    if not rows:
        return None
    return db.query(Ticket).filter(Ticket.id == tid).first()


@router.post("/tickets")
async def soumettre_question(payload: QuestionRequest):
    if payload.domaine.upper() not in DOMAINES_VALIDES:
        raise HTTPException(400, f"Domaine invalide : {payload.domaine}")
    if not payload.question.strip():
        raise HTTPException(400, "La question ne peut pas être vide")

    job = question_job.apply_async(
        args=[payload.question, payload.domaine.upper(), payload.user_id],
        queue="queue_questions",
    )

    return {
        "job_id": job.id,
        "question": payload.question,
        "domaine": payload.domaine.upper(),
        "statut": "EN_ATTENTE",
    }


@router.post("/tickets/{ticket_id}/suivi")
async def soumettre_suivi(ticket_id: str, payload: SuiviRequest):
    """Ajoute une précision au fil du ticket : relance le pipeline RAG sur le
    ticket existant (nouvelle réponse, la question d'origine est conservée)."""
    if not payload.question.strip():
        raise HTTPException(400, "La question ne peut pas être vide")
    tid = _parse_ticket_id(ticket_id)
    db = SessionLocal()
    try:
        ticket = db.query(Ticket).filter(Ticket.id == tid).first()
        if not ticket:
            raise HTTPException(404, "Ticket introuvable")
        if ticket.closed_at is not None:
            raise HTTPException(409, "Ticket clôturé : impossible d'ajouter une précision")
        domaine = ticket.domaine
        user_id = payload.user_id or (str(ticket.user_id) if ticket.user_id else None)
        # Marque le ticket « en cours » DÈS la soumission (avant même que le worker
        # ne tourne) pour que les badges des listes se mettent à jour au prochain
        # poll, sans attendre la fin du traitement. Le worker repassera statut_job
        # à TERMINÉ/ÉCHOUÉ et fixera le statut métier final.
        ticket.statut_job = "EN_ATTENTE"
        db.commit()
    finally:
        db.close()

    job = question_job.apply_async(
        args=[payload.question, domaine, user_id],
        kwargs={"ticket_id": ticket_id},
        queue="queue_questions",
    )
    return {
        "job_id": job.id,
        "ticket_id": ticket_id,
        "question": payload.question,
        "domaine": domaine,
        "statut": "EN_ATTENTE",
    }


@router.post("/tickets/{ticket_id}/cloturer")
async def cloturer_ticket(ticket_id: str, payload: CloturerRequest):
    """Clôture le ticket (l'utilisateur est satisfait). Idempotence refusée :
    un ticket déjà clôturé renvoie 409."""
    tid = _parse_ticket_id(ticket_id)
    db = SessionLocal()
    try:
        ticket = db.query(Ticket).filter(Ticket.id == tid).first()
        if not ticket:
            raise HTTPException(404, "Ticket introuvable")
        if ticket.closed_at is not None:
            raise HTTPException(409, "Ticket déjà clôturé")
        ticket.closed_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(ticket)
        return _serialize_ticket(ticket)
    finally:
        db.close()


@router.get("/tickets")
async def liste_tickets(
    page: int = 1,
    limit: int = 10,
    domaine: str | None = None,
    statut: str | None = None,
    user_id: str | None = None,
    closed: bool | None = None,
):
    db = SessionLocal()
    try:
        query = db.query(Ticket)
        if domaine:
            query = query.filter(Ticket.domaine == domaine.upper())
        if statut:
            query = query.filter(Ticket.statut_ticket == statut.upper())
        if closed is True:
            query = query.filter(Ticket.closed_at.isnot(None))
        elif closed is False:
            query = query.filter(Ticket.closed_at.is_(None))
        if user_id:
            try:
                query = query.filter(Ticket.user_id == uuid.UUID(user_id))
            except ValueError as e:
                raise HTTPException(400, "user_id invalide") from e
        total = query.count()
        tickets = (
            query.order_by(Ticket.created_at.desc())
            .offset((page - 1) * limit)
            .limit(limit)
            .all()
        )
        return {
            "total": total,
            "page": page,
            "limit": limit,
            "items": [_serialize_ticket(t) for t in tickets],
        }
    finally:
        db.close()


@router.get("/tickets/{ticket_id}/reponses")
async def reponses_par_ticket(ticket_id: str):
    from app.models.reponse import Reponse as ReponseModel
    db = SessionLocal()
    try:
        try:
            tid = uuid.UUID(ticket_id)
        except ValueError as e:
            raise HTTPException(400, "ticket_id invalide") from e
        ticket = db.query(Ticket).filter(Ticket.id == tid).first()
        if not ticket:
            raise HTTPException(404, "Ticket introuvable")
        reponses = (
            db.query(ReponseModel)
            .filter(ReponseModel.ticket_id == tid)
            .order_by(ReponseModel.created_at.asc())
            .all()
        )
        return [
            {
                "id": str(r.id),
                "ticket_id": str(r.ticket_id),
                "contenu": r.contenu,
                "contenu_corrige": r.contenu_corrige,
                "question_suivi": r.question_suivi,
                "statut": r.statut,
                "source": r.source,
                "nb_validations": r.nb_validations,
                "canonique": r.canonique,
                "score_similarite": r.score_similarite,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in reponses
        ]
    finally:
        db.close()


@router.get("/tickets/{ticket_id}")
async def get_ticket(ticket_id: str):
    db = SessionLocal()
    try:
        try:
            tid = uuid.UUID(ticket_id)
        except ValueError as e:
            raise HTTPException(400, "ticket_id invalide") from e
        ticket = db.query(Ticket).filter(Ticket.id == tid).first()
        if not ticket:
            raise HTTPException(404, "Ticket introuvable")
        return _serialize_ticket(ticket)
    finally:
        db.close()


def _parse_ticket_id(ticket_id: str) -> uuid.UUID:
    try:
        return uuid.UUID(ticket_id)
    except ValueError as e:
        raise HTTPException(400, "ticket_id invalide") from e


@router.post("/tickets/{ticket_id}/lock")
async def verrouiller_ticket(ticket_id: str, payload: LockRequest):
    """Prend (ou prolonge) le verrou du ticket pour le validateur courant."""
    tid = _parse_ticket_id(ticket_id)
    db = SessionLocal()
    try:
        if not db.query(Ticket).filter(Ticket.id == tid).first():
            raise HTTPException(404, "Ticket introuvable")

        ticket = _acquire_lock(db, tid, payload.validator_id)
        if ticket is None:
            # Détenu par un autre validateur, bail encore valide → conflit
            ticket = db.query(Ticket).filter(Ticket.id == tid).first()
            raise HTTPException(
                409,
                {
                    "message": "Ticket verrouillé par un autre validateur.",
                    **lock_info(ticket),
                },
            )
        return {"ticket_id": ticket_id, "is_mine": True, **lock_info(ticket)}
    finally:
        db.close()


@router.post("/tickets/{ticket_id}/heartbeat")
async def heartbeat_ticket(ticket_id: str, payload: LockRequest):
    """Prolonge le bail tant que le validateur garde le ticket ouvert."""
    tid = _parse_ticket_id(ticket_id)
    db = SessionLocal()
    try:
        ticket = _acquire_lock(db, tid, payload.validator_id)
        if ticket is None:
            ticket = db.query(Ticket).filter(Ticket.id == tid).first()
            if not ticket:
                raise HTTPException(404, "Ticket introuvable")
            raise HTTPException(
                409,
                {
                    "message": "Verrou perdu au profit d'un autre validateur.",
                    **lock_info(ticket),
                },
            )
        return {"ticket_id": ticket_id, "is_mine": True, **lock_info(ticket)}
    finally:
        db.close()


@router.post("/tickets/{ticket_id}/unlock", status_code=204)
async def deverrouiller_ticket(ticket_id: str, payload: LockRequest):
    """Libère le verrou (uniquement si détenu par ce validateur). Idempotent."""
    tid = _parse_ticket_id(ticket_id)
    db = SessionLocal()
    try:
        db.query(Ticket).filter(
            Ticket.id == tid,
            Ticket.locked_by == payload.validator_id,
        ).update(
            {
                Ticket.locked_by: None,
                Ticket.locked_at: None,
                Ticket.lock_expires_at: None,
            },
            synchronize_session=False,
        )
        db.commit()
    finally:
        db.close()


@router.get("/tickets/{job_id}/status")
async def statut_ticket(job_id: str):
    # Statut Celery
    result = AsyncResult(job_id, app=celery_app)

    reponse = {
        "job_id": job_id,
        "statut_job": result.status,
    }

    # Si le job est terminé, enrichit avec les données PostgreSQL
    if result.status == "SUCCESS":
        job_result = result.result

        reponse["branche"] = job_result.get("branche")
        reponse["question"] = job_result.get("question")
        reponse["domaine"] = job_result.get("domaine")
        reponse["reponse"] = job_result.get("reponse")

        # Récupère le statut métier depuis PostgreSQL
        ticket_id = job_result.get("ticket_id")
        if ticket_id:
            db = SessionLocal()
            try:
                ticket = (
                    db.query(Ticket).filter(Ticket.id == uuid.UUID(ticket_id)).first()
                )
                if ticket:
                    reponse["statut_ticket"] = ticket.statut_ticket
                    reponse["ticket_id"] = ticket_id
            finally:
                db.close()

    elif result.status == "FAILURE":
        reponse["erreur"] = str(result.result)

    return reponse
