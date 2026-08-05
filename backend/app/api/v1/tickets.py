import asyncio
import uuid
from datetime import datetime, timedelta, timezone

from celery.result import AsyncResult
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import exists, or_
from sqlalchemy.orm import joinedload

from app.config import settings
from app.core.security import CurrentUser
from app.database import SessionLocal
from app.models.groupe import Groupe
from app.models.groupe import user_groups as ug_table
from app.models.reponse import Reponse as ReponseModel
from app.models.ticket import Ticket
from app.models.ticket_event import TicketEvent
from app.models.user import User
from app.services.broadcast import broadcast_async
from app.workers.celery_app import celery_app
from app.workers.question import question_job

router = APIRouter()

# L'identité (user_id / validator_id) est désormais dérivée du JWT via
# get_current_user, et non plus transmise dans le corps des requêtes.


class QuestionRequest(BaseModel):
    question: str
    objet: str | None = None
    domaine: str


class SuiviRequest(BaseModel):
    question: str


def _full_name(user) -> str | None:
    return " ".join(filter(None, [user.prenom, user.nom])) or None if user else None


def lock_info(ticket: Ticket, now: datetime | None = None) -> dict:
    """Sérialise l'état du verrou. Un bail expiré est considéré comme libre."""
    now = now or datetime.now(timezone.utc)
    actif = bool(ticket.locked_by and ticket.lock_expires_at and ticket.lock_expires_at > now)
    return {
        "locked_by": str(ticket.locked_by) if actif else None,
        "locked_by_email": ticket.locker.email if actif and ticket.locker else None,
        "lock_expires_at": ticket.lock_expires_at.isoformat() if actif else None,
    }


def _serialize_ticket(ticket: Ticket) -> dict:
    return {
        "id": str(ticket.id),
        "question": ticket.question,
        "objet": ticket.objet,
        "domaine": ticket.domaine,
        "statut_ticket": ticket.statut_ticket,
        "statut_job": ticket.statut_job,
        "user_id": str(ticket.user_id) if ticket.user_id else None,
        "user_email": ticket.user.email if ticket.user else None,
        "user_nom_complet": _full_name(ticket.user),
        "user_departement": ticket.user.departement if ticket.user else None,
        "user_titre": ticket.user.titre if ticket.user else None,
        "user_telephone": ticket.user.telephone if ticket.user else None,
        "user_localisation": ticket.user.localisation if ticket.user else None,
        "canonique": ticket.canonique,
        "created_at": ticket.created_at.isoformat() if ticket.created_at else None,
        "closed_at": ticket.closed_at.isoformat() if ticket.closed_at else None,
        **lock_info(ticket),
        "assigned_to": str(ticket.assigned_to) if ticket.assigned_to else None,
        "assigned_to_email": ticket.assignee.email if ticket.assignee else None,
        "assigned_to_nom_complet": _full_name(ticket.assignee),
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


@router.get("/tickets/domaines")
async def list_domaines(_: CurrentUser):
    """Liste les domaines disponibles (tout utilisateur authentifié)."""
    db = SessionLocal()
    try:
        rows = db.query(Groupe.domaine).distinct().order_by(Groupe.domaine).all()
        return [r[0] for r in rows]
    finally:
        db.close()


@router.post("/tickets")
async def soumettre_question(payload: QuestionRequest, current_user: CurrentUser):
    domaine = payload.domaine.upper()
    db = SessionLocal()
    try:
        domaines_valides = {r[0] for r in db.query(Groupe.domaine).distinct().all()}
    finally:
        db.close()
    if not domaines_valides:
        raise HTTPException(400, "Aucun domaine configuré. Contactez un administrateur.")
    if domaine not in domaines_valides:
        raise HTTPException(400, f"Domaine invalide : {domaine}")
    if not payload.question.strip():
        raise HTTPException(400, "La question ne peut pas être vide")

    job = question_job.apply_async(
        args=[payload.question, domaine, str(current_user.id)],
        kwargs={"objet": payload.objet},
        queue="queue_questions",
    )

    return {
        "job_id": job.id,
        "question": payload.question,
        "domaine": domaine,
        "statut": "EN_ATTENTE",
    }


@router.post("/tickets/{ticket_id}/suivi")
async def soumettre_suivi(
    ticket_id: str,
    payload: SuiviRequest,
    current_user: CurrentUser,
):
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
        user_id = str(current_user.id)
        ticket.statut_job = "EN_ATTENTE"
        db.commit()
    finally:
        db.close()

    job = question_job.apply_async(
        args=[payload.question, domaine, user_id],
        kwargs={"ticket_id": ticket_id},
        queue="queue_questions",
    )
    await broadcast_async(f"sse:domain:{domaine}", "ticket_followup", {"ticket_id": ticket_id, "domaine": domaine})
    return {
        "job_id": job.id,
        "ticket_id": ticket_id,
        "question": payload.question,
        "domaine": domaine,
        "statut": "EN_ATTENTE",
    }


@router.post("/tickets/{ticket_id}/cloturer")
async def cloturer_ticket(ticket_id: str, current_user: CurrentUser):
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
        domaine = ticket.domaine
        ticket.closed_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(ticket)
        result = _serialize_ticket(ticket)
    finally:
        db.close()
    await broadcast_async(f"sse:domain:{domaine}", "ticket_closed", {"ticket_id": ticket_id, "domaine": domaine})
    return result


@router.get("/tickets")
async def liste_tickets(
    current_user: CurrentUser,
    page: int = 1,
    limit: int = 10,
    domaine: str | None = None,
    domaines: str | None = None,
    statut: str | None = None,
    user_id: str | None = None,
    closed: bool | None = None,
    search: str | None = None,
    disponibles: bool | None = None,
):
    db = SessionLocal()
    try:
        query = db.query(Ticket)
        if domaines:
            domaine_list = [d.strip().upper() for d in domaines.split(",") if d.strip()]
            query = query.filter(Ticket.domaine.in_(domaine_list))
        elif domaine:
            query = query.filter(Ticket.domaine == domaine.upper())
        if disponibles:
            # Exclut les tickets assignés à quelqu'un d'autre que l'utilisateur courant
            query = query.filter(
                or_(
                    Ticket.assigned_to.is_(None),
                    Ticket.assigned_to == current_user.id,
                )
            )
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
        if search:
            try:
                tid = uuid.UUID(search)
                query = query.filter(Ticket.id == tid)
            except ValueError:
                pattern = f"%{search}%"
                query = query.filter(
                    or_(
                        Ticket.objet.ilike(pattern),
                        Ticket.question.ilike(pattern),
                    )
                )
        total = query.count()
        tickets = query.order_by(Ticket.created_at.desc()).offset((page - 1) * limit).limit(limit).all()
        return {
            "total": total,
            "page": page,
            "limit": limit,
            "items": [_serialize_ticket(t) for t in tickets],
        }
    finally:
        db.close()


@router.get("/tickets/mes-assignations")
async def mes_assignations(current_user: CurrentUser):
    """Tickets ouverts assignés à l'utilisateur courant (pour la cloche de notifications)."""
    db = SessionLocal()
    try:
        tickets = (
            db.query(Ticket)
            .filter(Ticket.assigned_to == current_user.id, Ticket.closed_at.is_(None))
            .order_by(Ticket.created_at.desc())
            .all()
        )
        return [_serialize_ticket(t) for t in tickets]
    finally:
        db.close()


@router.get("/tickets/domaines/{domaine}/validateurs")
async def validateurs_par_domaine(domaine: str, _: CurrentUser):
    """Liste les membres du groupe pour un domaine donné (tout utilisateur authentifié)."""
    db = SessionLocal()
    try:
        groupe = (
            db.query(Groupe)
            .options(joinedload(Groupe.membres))
            .filter(Groupe.domaine == domaine.upper())
            .first()
        )
        if not groupe:
            return []
        return [
            {"id": str(u.id), "email": u.email, "prenom": u.prenom, "nom": u.nom}
            for u in groupe.membres
        ]
    finally:
        db.close()


class AssignerRequest(BaseModel):
    assignee_id: uuid.UUID


@router.post("/tickets/{ticket_id}/assigner")
async def assigner_ticket(ticket_id: str, payload: AssignerRequest, current_user: CurrentUser):
    """Assigne le ticket à un validateur du même domaine."""
    tid = _parse_ticket_id(ticket_id)
    db = SessionLocal()
    try:
        ticket = db.query(Ticket).filter(Ticket.id == tid).first()
        if not ticket:
            raise HTTPException(404, "Ticket introuvable")
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
        # Libère tout verrou existant : seul l'assigné peut maintenant éditer
        ticket.locked_by = None
        ticket.locked_at = None
        ticket.lock_expires_at = None
        assignee = db.query(User).filter(User.id == payload.assignee_id).first()
        db.add(TicketEvent(
            ticket_id=tid,
            type="ASSIGNE",
            actor_id=current_user.id,
            actor_email=current_user.email,
            actor_nom_complet=_full_name(current_user),
            meta={
                "assignee_id": str(payload.assignee_id),
                "assignee_email": assignee.email if assignee else None,
                "assignee_nom": _full_name(assignee) if assignee else None,
            },
        ))
        db.commit()
        result = _serialize_ticket(ticket)
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
async def desassigner_ticket(ticket_id: str, current_user: CurrentUser):
    """Remet le ticket dans le pot commun (supprime l'assignation)."""
    tid = _parse_ticket_id(ticket_id)
    db = SessionLocal()
    try:
        ticket = db.query(Ticket).filter(Ticket.id == tid).first()
        if not ticket:
            raise HTTPException(404, "Ticket introuvable")
        domaine = ticket.domaine
        ticket.assigned_to = None
        db.add(TicketEvent(
            ticket_id=tid,
            type="DESASSIGNE",
            actor_id=current_user.id,
            actor_email=current_user.email,
            actor_nom_complet=_full_name(current_user),
            meta={},
        ))
        db.commit()
        result = _serialize_ticket(ticket)
    finally:
        db.close()
    await broadcast_async(f"sse:domain:{domaine}", "ticket_unassigned", {"ticket_id": ticket_id, "domaine": domaine})
    return result


@router.get("/tickets/participated")
async def tickets_avec_participation(
    current_user: CurrentUser,
    page: int = 1,
    limit: int = 10,
):
    from app.models.reponse import Reponse as ReponseModel

    db = SessionLocal()
    try:
        base_query = (
            db.query(Ticket)
            .join(ReponseModel, ReponseModel.ticket_id == Ticket.id)
            .filter(ReponseModel.validator_id == current_user.id)
            .distinct()
        )
        total = base_query.count()
        tickets = base_query.order_by(Ticket.created_at.desc()).offset((page - 1) * limit).limit(limit).all()
        return {
            "total": total,
            "page": page,
            "limit": limit,
            "items": [_serialize_ticket(t) for t in tickets],
        }
    finally:
        db.close()


@router.get("/tickets/{ticket_id}/reponses")
async def reponses_par_ticket(ticket_id: str, current_user: CurrentUser):
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
            db.query(ReponseModel).filter(ReponseModel.ticket_id == tid).order_by(ReponseModel.created_at.asc()).all()
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
                "validator_email": r.validator.email if r.validator else None,
                "validator_nom_complet": _full_name(r.validator) or (r.validator.email if r.validator else None),
            }
            for r in reponses
        ]
    finally:
        db.close()


@router.get("/tickets/{ticket_id}/workflow")
async def get_ticket_workflow(ticket_id: str, _: CurrentUser):
    """Retourne la timeline complète du ticket, triée chronologiquement."""
    db = SessionLocal()
    try:
        tid = _parse_ticket_id(ticket_id)
        ticket = db.query(Ticket).filter(Ticket.id == tid).first()
        if not ticket:
            raise HTTPException(404, "Ticket introuvable")

        reponses = (
            db.query(ReponseModel)
            .filter(ReponseModel.ticket_id == tid)
            .order_by(ReponseModel.created_at.asc())
            .all()
        )
        ticket_events = (
            db.query(TicketEvent)
            .filter(TicketEvent.ticket_id == tid)
            .order_by(TicketEvent.created_at.asc())
            .all()
        )

        _TYPE_ORDER = {
            "CREE": 0, "SUIVI": 1, "REPONSE_GENEREE": 2,
            "ASSIGNE": 3, "DESASSIGNE": 3,
            "VALIDE": 4, "CORRIGE": 4, "REJETE": 4,
            "CLOTURE": 5,
        }

        events: list[dict] = []

        events.append({
            "type": "CREE",
            "at": ticket.created_at.isoformat() if ticket.created_at else None,
            "actor_email": ticket.user.email if ticket.user else None,
            "actor_nom_complet": _full_name(ticket.user),
            "meta": {"domaine": ticket.domaine},
        })

        type_map = {"VALIDÉE": "VALIDE", "CORRIGÉE": "CORRIGE", "REJETÉE": "REJETE"}
        for reponse in reponses:
            ts = reponse.created_at.isoformat() if reponse.created_at else None
            if reponse.question_suivi:
                events.append({
                    "type": "SUIVI",
                    "at": ts,
                    "actor_email": None,
                    "actor_nom_complet": None,
                    "meta": {"texte": reponse.question_suivi},
                })
            events.append({
                "type": "REPONSE_GENEREE",
                "at": ts,
                "actor_email": None,
                "actor_nom_complet": None,
                "meta": {"source": reponse.source},
            })
            if reponse.validated_at and reponse.statut in type_map:
                events.append({
                    "type": type_map[reponse.statut],
                    "at": reponse.validated_at.isoformat(),
                    "actor_email": reponse.validator.email if reponse.validator else None,
                    "actor_nom_complet": _full_name(reponse.validator),
                    "meta": {},
                })

        for evt in ticket_events:
            events.append({
                "type": evt.type,
                "at": evt.created_at.isoformat() if evt.created_at else None,
                "actor_email": evt.actor_email,
                "actor_nom_complet": evt.actor_nom_complet,
                "meta": evt.meta or {},
            })

        if ticket.closed_at:
            events.append({
                "type": "CLOTURE",
                "at": ticket.closed_at.isoformat(),
                "actor_email": None,
                "actor_nom_complet": None,
                "meta": {},
            })

        events.sort(key=lambda e: (e["at"] or "", _TYPE_ORDER.get(e["type"], 6)))
        return events
    finally:
        db.close()


@router.get("/tickets/{ticket_id}")
async def get_ticket(ticket_id: str, current_user: CurrentUser):
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
async def verrouiller_ticket(ticket_id: str, current_user: CurrentUser):
    """Prend (ou prolonge) le verrou du ticket pour le validateur courant."""
    tid = _parse_ticket_id(ticket_id)
    db = SessionLocal()
    try:
        existing = db.query(Ticket).filter(Ticket.id == tid).first()
        if not existing:
            raise HTTPException(404, "Ticket introuvable")
        domaine = existing.domaine

        # Un ticket assigné à quelqu'un d'autre ne peut pas être verrouillé
        if existing.assigned_to and existing.assigned_to != current_user.id:
            raise HTTPException(
                409,
                {
                    "message": "Ce ticket est assigné à un autre validateur.",
                    "locked_by_email": existing.assignee.email if existing.assignee else None,
                    "lock_expires_at": None,
                    "is_assigned": True,
                },
            )

        ticket = _acquire_lock(db, tid, current_user.id)
        if ticket is None:
            ticket = db.query(Ticket).filter(Ticket.id == tid).first()
            raise HTTPException(
                409,
                {
                    "message": "Ticket verrouillé par un autre validateur.",
                    **lock_info(ticket),
                },
            )
        result = {"ticket_id": ticket_id, "is_mine": True, **lock_info(ticket)}
    finally:
        db.close()
    await broadcast_async(
        f"sse:domain:{domaine}", "ticket_locked",
        {"ticket_id": ticket_id, "locked_by_email": current_user.email},
    )
    return result


@router.post("/tickets/{ticket_id}/heartbeat")
async def heartbeat_ticket(ticket_id: str, current_user: CurrentUser):
    """Prolonge le bail tant que le validateur garde le ticket ouvert."""
    tid = _parse_ticket_id(ticket_id)
    db = SessionLocal()
    try:
        ticket = _acquire_lock(db, tid, current_user.id)
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
async def deverrouiller_ticket(ticket_id: str, current_user: CurrentUser):
    """Libère le verrou (uniquement si détenu par ce validateur). Idempotent."""
    tid = _parse_ticket_id(ticket_id)
    db = SessionLocal()
    domaine = None
    try:
        ticket = db.query(Ticket).filter(Ticket.id == tid).first()
        if ticket:
            domaine = ticket.domaine
        db.query(Ticket).filter(
            Ticket.id == tid,
            Ticket.locked_by == current_user.id,
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
    if domaine:
        await broadcast_async(f"sse:domain:{domaine}", "ticket_unlocked", {"ticket_id": ticket_id})


@router.get("/tickets/{job_id}/status")
async def statut_ticket(job_id: str, current_user: CurrentUser):
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
                ticket = db.query(Ticket).filter(Ticket.id == uuid.UUID(ticket_id)).first()
                if ticket:
                    reponse["statut_ticket"] = ticket.statut_ticket
                    reponse["ticket_id"] = ticket_id
            finally:
                db.close()

    elif result.status == "FAILURE":
        reponse["erreur"] = str(result.result)

    return reponse
