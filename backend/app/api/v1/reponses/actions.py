from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from app.config import settings
from app.core.permissions import check_domain_write
from app.core.security import BackofficeUser
from app.database import SessionLocal
from app.models.reponse import Reponse
from app.models.reponse_chunk import ReponseChunk
from app.models.ticket import Ticket
from app.schemas.reponse import CorrigerRequest, EditerCanoniqueRequest, RejeterRequest
from app.services.broadcast import broadcast_async
from app.services.obsolescence import (
    RAISON_MANUELLE,
    confirmer_actualite,
    fermeture_copies,
    lever_a_relire,
    requeuer_en_attente,
    retirer_du_service,
)
from app.services.qdrant import delete_response_point
from app.services.reponse_service import (
    check_reponse_write,
    get_reponse_or_404,
    liberer_verrou,
    notifier_employe,
    verifier_auto_validation,
    verifier_etat_initial,
    verifier_verrou,
)
from app.workers.feedback import feedback_job

router = APIRouter()


@router.post("/reponses/{reponse_id}/valider")
async def valider_reponse(reponse_id: str, current_user: BackofficeUser):
    db = SessionLocal()
    try:
        reponse = get_reponse_or_404(db, reponse_id)
        verifier_etat_initial(reponse)

        ticket = db.query(Ticket).filter(Ticket.id == reponse.ticket_id).first()
        if ticket:
            check_domain_write(ticket.domaine, current_user)
        verifier_auto_validation(reponse, current_user.id, ticket)
        verifier_verrou(ticket, current_user.id)

        reponse.statut = "VALIDÉE"
        reponse.validator_id = current_user.id
        reponse.validated_at = datetime.now(timezone.utc)

        if ticket:
            ticket.statut_ticket = "VALIDÉ"
            ticket.validated_at = datetime.now(timezone.utc)
            liberer_verrou(ticket)

        reponse_source = None
        if reponse.reponse_source_id:
            reponse_source = db.query(Reponse).filter(Reponse.id == reponse.reponse_source_id).first()
            if reponse_source:
                reponse_source.nb_validations += 1
                if reponse_source.nb_validations >= settings.seuil_canonique:
                    reponse_source.canonique = True
        else:
            reponse.nb_validations += 1
            if reponse.nb_validations >= settings.seuil_canonique:
                reponse.canonique = True

        notifier_employe(db, ticket, reponse_id, current_user.id)
        db.commit()

        if reponse.reponse_source_id and reponse_source:
            feedback_job.apply_async(args=[str(reponse_source.id)], queue="queue_ingestion")
        elif not reponse.reponse_source_id:
            feedback_job.apply_async(args=[reponse_id], queue="queue_ingestion")

        domaine = ticket.domaine if ticket else None
        ticket_id_str = str(reponse.ticket_id)
        user_id = str(ticket.user_id) if ticket and ticket.user_id else None
        result = {
            "reponse_id": reponse_id,
            "statut": "VALIDÉE",
            "nb_validations": reponse.nb_validations,
            "canonique": reponse.canonique,
            "validated_at": reponse.validated_at.isoformat(),
            "message": ("Réponse validée et indexée comme canonique." if reponse.canonique else "Réponse validée."),
        }
    finally:
        db.close()

    if domaine:
        await broadcast_async(
            f"sse:domain:{domaine}", "reponse_validated", {"ticket_id": ticket_id_str, "domaine": domaine}
        )
    if user_id:
        await broadcast_async(f"sse:user:{user_id}", "notification_created", {"ticket_id": ticket_id_str})
    return result


@router.post("/reponses/{reponse_id}/rejeter")
async def rejeter_reponse(reponse_id: str, payload: RejeterRequest, current_user: BackofficeUser):
    db = SessionLocal()
    try:
        reponse = get_reponse_or_404(db, reponse_id)
        verifier_etat_initial(reponse)

        ticket = db.query(Ticket).filter(Ticket.id == reponse.ticket_id).first()
        if ticket:
            check_domain_write(ticket.domaine, current_user)
        verifier_auto_validation(reponse, current_user.id, ticket)
        verifier_verrou(ticket, current_user.id)

        reponse.statut = "REJETÉE"
        reponse.validator_id = current_user.id
        reponse.validated_at = datetime.now(timezone.utc)

        if ticket:
            ticket.statut_ticket = "REJETÉ"
            liberer_verrou(ticket)

        domaine = ticket.domaine if ticket else None
        ticket_id_str = str(reponse.ticket_id)
        db.commit()
    finally:
        db.close()

    print(f"[VALIDATION] ❌ Réponse {reponse_id} rejetée par {current_user.id}")
    if domaine:
        await broadcast_async(
            f"sse:domain:{domaine}", "reponse_rejected", {"ticket_id": ticket_id_str, "domaine": domaine}
        )
    return {
        "reponse_id": reponse_id,
        "statut": "REJETÉE",
        "raison": payload.raison,
        "message": "Réponse rejetée.",
    }


@router.put("/reponses/{reponse_id}/corriger")
async def corriger_reponse(reponse_id: str, payload: CorrigerRequest, current_user: BackofficeUser):
    db = SessionLocal()
    try:
        reponse = get_reponse_or_404(db, reponse_id)
        verifier_etat_initial(reponse)

        if not payload.contenu_corrige.strip():
            raise HTTPException(400, "Le contenu corrigé ne peut pas être vide.")

        ticket = db.query(Ticket).filter(Ticket.id == reponse.ticket_id).first()
        if ticket:
            check_domain_write(ticket.domaine, current_user)
        verifier_auto_validation(reponse, current_user.id, ticket)
        verifier_verrou(ticket, current_user.id)

        reponse.statut = "CORRIGÉE"
        reponse.contenu_corrige = payload.contenu_corrige
        reponse.validator_id = current_user.id
        reponse.validated_at = datetime.now(timezone.utc)

        if reponse.a_relire:
            lever_a_relire(reponse)

        if ticket:
            ticket.statut_ticket = "VALIDÉ"
            ticket.validated_at = datetime.now(timezone.utc)
            liberer_verrou(ticket)

        notifier_employe(db, ticket, reponse_id, current_user.id)
        domaine = ticket.domaine if ticket else None
        ticket_id_str = str(reponse.ticket_id)
        user_id = str(ticket.user_id) if ticket and ticket.user_id else None
        db.commit()
    finally:
        db.close()

    print(f"[CORRECTION] ✏️  Réponse {reponse_id} corrigée et en cours d'indexation dans Qdrant.")
    feedback_job.apply_async(args=[reponse_id], queue="queue_ingestion")
    if domaine:
        await broadcast_async(
            f"sse:domain:{domaine}", "reponse_corrected", {"ticket_id": ticket_id_str, "domaine": domaine}
        )
    if user_id:
        await broadcast_async(f"sse:user:{user_id}", "notification_created", {"ticket_id": ticket_id_str})
    return {
        "reponse_id": reponse_id,
        "statut": "CORRIGÉE",
        "contenu_corrige": payload.contenu_corrige,
        "message": "Réponse corrigée.",
    }


@router.post("/reponses/{reponse_id}/retirer")
async def retirer_reponse(reponse_id: str, current_user: BackofficeUser):
    """Retire du service une réponse relue et jugée dépassée."""
    db = SessionLocal()
    try:
        reponse = get_reponse_or_404(db, reponse_id)
        check_reponse_write(db, reponse, current_user)

        if not reponse.a_relire:
            raise HTTPException(409, "Cette réponse n'est pas signalée à relire.")

        doc_id, version = reponse.a_relire_doc_id, reponse.a_relire_version
        famille = fermeture_copies(db, {reponse.id})
        cibles = db.query(Reponse).filter(Reponse.id.in_(famille), Reponse.obsolete.is_(False)).all()
        en_attente_cibles = [r for r in cibles if r.statut == "EN_ATTENTE"]
        retirer_du_service(db, cibles, RAISON_MANUELLE, doc_id, version)
        requeuer_en_attente(db, en_attente_cibles)
        nb = len(cibles)
    finally:
        db.close()

    await broadcast_async("sse:admin", "saved_answers_updated", {"reponse_id": reponse_id})
    return {
        "reponse_id": reponse_id,
        "nb_retirees": nb,
        "message": "Réponse retirée du service. Elle reste restaurable depuis l'onglet Obsolètes.",
    }


@router.post("/reponses/{reponse_id}/restaurer")
async def restaurer_reponse(reponse_id: str, current_user: BackofficeUser):
    """Remet en service une réponse déclarée obsolète."""
    db = SessionLocal()
    try:
        reponse = get_reponse_or_404(db, reponse_id)
        if not reponse.obsolete:
            raise HTTPException(409, "Cette réponse n'est pas obsolète.")

        check_reponse_write(db, reponse, current_user)

        famille = fermeture_copies(db, {reponse.id})
        a_reindexer = [
            str(r[0]) for r in db.query(Reponse.id).filter(Reponse.id.in_(famille), Reponse.obsolete.is_(True)).all()
        ]
        db.query(Reponse).filter(Reponse.id.in_(famille)).update(
            {
                "obsolete": False,
                "obsolete_raison": None,
                "obsolete_doc_id": None,
                "obsolete_version": None,
                "obsolete_at": None,
                "a_relire": False,
                "a_relire_raison": None,
                "a_relire_doc_id": None,
                "a_relire_version": None,
                "a_relire_at": None,
            },
            synchronize_session=False,
        )
        db.commit()
    finally:
        db.close()

    for rid in a_reindexer:
        feedback_job.apply_async(args=[rid], queue="queue_ingestion")

    await broadcast_async("sse:admin", "saved_answers_updated", {"reponse_id": reponse_id})
    return {
        "reponse_id": reponse_id,
        "nb_restaurees": len(a_reindexer),
        "message": "Réponse restaurée et en cours de réindexation.",
    }


@router.put("/reponses/{reponse_id}/editer")
async def editer_reponse_canonique(
    reponse_id: str,
    payload: EditerCanoniqueRequest,
    current_user: BackofficeUser,
):
    """Édite le contenu servi d'une réponse canonique puis la réindexe dans Qdrant."""
    db = SessionLocal()
    try:
        reponse = get_reponse_or_404(db, reponse_id)
        check_reponse_write(db, reponse, current_user)

        if not reponse.canonique and not reponse.a_relire:
            raise HTTPException(409, "Seules les réponses canoniques peuvent être éditées ici.")

        if not payload.contenu.strip():
            raise HTTPException(400, "Le contenu ne peut pas être vide.")

        reponse.contenu_corrige = payload.contenu
        if reponse.a_relire:
            confirmer_actualite(db, db.query(Reponse).filter(Reponse.id.in_(fermeture_copies(db, {reponse.id}))).all())
        db.commit()
    finally:
        db.close()

    feedback_job.apply_async(args=[reponse_id], queue="queue_ingestion")
    await broadcast_async("sse:admin", "saved_answers_updated", {"reponse_id": reponse_id})
    return {
        "reponse_id": reponse_id,
        "contenu_corrige": payload.contenu,
        "message": "Réponse canonique éditée et en cours de réindexation.",
    }


@router.delete("/reponses/{reponse_id}")
async def supprimer_reponse_canonique(reponse_id: str, current_user: BackofficeUser):
    """Supprime définitivement une réponse canonique."""
    db = SessionLocal()
    try:
        reponse = get_reponse_or_404(db, reponse_id)
        check_reponse_write(db, reponse, current_user)

        if not reponse.canonique and not reponse.obsolete:
            raise HTTPException(409, "Seules les réponses canoniques peuvent être supprimées ici.")

        famille = fermeture_copies(db, {reponse.id})
        copies = db.query(Reponse).filter(Reponse.id.in_(famille), Reponse.id != reponse.id).all()
        en_attente_copies = [r for r in copies if r.statut == "EN_ATTENTE" and not r.obsolete]
        requeuer_en_attente(db, en_attente_copies)

        for copie in copies:
            if not copie.obsolete:
                delete_response_point(str(copie.id))
            db.query(ReponseChunk).filter(ReponseChunk.reponse_id == copie.id).delete(synchronize_session=False)
            db.delete(copie)
        db.flush()

        delete_response_point(reponse_id)
        db.query(ReponseChunk).filter(ReponseChunk.reponse_id == reponse.id).delete(synchronize_session=False)
        db.delete(reponse)
        db.commit()
    finally:
        db.close()

    await broadcast_async("sse:admin", "saved_answers_updated", {"reponse_id": reponse_id})
    return {
        "reponse_id": reponse_id,
        "message": "Réponse canonique supprimée.",
    }
