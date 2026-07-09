import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from app.database import SessionLocal
from app.models.reponse import Reponse
from app.models.ticket import Ticket
from app.schemas.reponse import CorrigerRequest, RejeterRequest, ValiderRequest
from app.workers.feedback import feedback_job

router = APIRouter()

ETATS_FINAUX = {"VALIDÉE", "REJETÉE", "CORRIGÉE"}


def get_reponse_or_404(db, reponse_id: str) -> Reponse:
    reponse = db.query(Reponse).filter(Reponse.id == uuid.UUID(reponse_id)).first()
    if not reponse:
        raise HTTPException(404, f"Réponse {reponse_id} introuvable")
    return reponse


def verifier_etat_initial(reponse: Reponse):
    if reponse.statut in ETATS_FINAUX:
        raise HTTPException(
            409,
            f"Réponse déjà traitée (statut={reponse.statut}). "
            f"Seules les réponses EN_ATTENTE peuvent être traitées.",
        )


def verifier_auto_validation(reponse: Reponse, validator_id: uuid.UUID, ticket: Ticket):
    if ticket and ticket.user_id and ticket.user_id == validator_id:
        raise HTTPException(
            403, "Un validateur ne peut pas traiter ses propres tickets."
        )


@router.post("/reponses/{reponse_id}/valider")
async def valider_reponse(reponse_id: str, payload: ValiderRequest):
    db = SessionLocal()
    try:
        reponse = get_reponse_or_404(db, reponse_id)
        verifier_etat_initial(reponse)

        ticket = db.query(Ticket).filter(Ticket.id == reponse.ticket_id).first()
        verifier_auto_validation(reponse, payload.validator_id, ticket)

        # Transition EN_ATTENTE → VALIDÉE
        reponse.statut = "VALIDÉE"
        reponse.validator_id = payload.validator_id
        reponse.validated_at = datetime.now(timezone.utc)

        if ticket:
            ticket.statut_ticket = "VALIDÉ"

        db.commit()

        # Feedback job to reindex the validated response in Qdrant
        print(f"[VALIDATION] ✅ Réponse {reponse_id} validée et en cours d'indexation dans Qdrant.")
        feedback_job.apply_async(args=[reponse_id], queue="queue_ingestion")

        print(
            f"[VALIDATION] ✅ Réponse {reponse_id} validée par {payload.validator_id}"
        )

        return {
            "reponse_id": reponse_id,
            "statut": "VALIDÉE",
            "validated_at": reponse.validated_at.isoformat(),
            "message": "Réponse validée.",
        }
    finally:
        db.close()


@router.post("/reponses/{reponse_id}/rejeter")
async def rejeter_reponse(reponse_id: str, payload: RejeterRequest):
    db = SessionLocal()
    try:
        reponse = get_reponse_or_404(db, reponse_id)
        verifier_etat_initial(reponse)

        ticket = db.query(Ticket).filter(Ticket.id == reponse.ticket_id).first()
        verifier_auto_validation(reponse, payload.validator_id, ticket)

        # Transition EN_ATTENTE → REJETÉE
        reponse.statut = "REJETÉE"
        reponse.validator_id = payload.validator_id
        reponse.validated_at = datetime.now(timezone.utc)

        if ticket:
            ticket.statut_ticket = "REJETÉ"

        db.commit()

        print(
            f"[VALIDATION] ❌ Réponse {reponse_id} rejetée par {payload.validator_id}"
        )

        return {
            "reponse_id": reponse_id,
            "statut": "REJETÉE",
            "raison": payload.raison,
            "message": "Réponse rejetée.",
        }
    finally:
        db.close()


@router.put("/reponses/{reponse_id}/corriger")
async def corriger_reponse(reponse_id: str, payload: CorrigerRequest):
    db = SessionLocal()
    try:
        reponse = get_reponse_or_404(db, reponse_id)
        verifier_etat_initial(reponse)

        if not payload.contenu_corrige.strip():
            raise HTTPException(400, "Le contenu corrigé ne peut pas être vide.")

        ticket = db.query(Ticket).filter(Ticket.id == reponse.ticket_id).first()
        verifier_auto_validation(reponse, payload.validator_id, ticket)

        # Transition EN_ATTENTE → CORRIGÉE
        reponse.statut = "CORRIGÉE"
        reponse.contenu_corrige = payload.contenu_corrige
        reponse.validator_id = payload.validator_id
        reponse.validated_at = datetime.now(timezone.utc)

        if ticket:
            ticket.statut_ticket = "VALIDÉ"

        db.commit()

        # Feedback job to reindex the validated response in Qdrant
        print(f"[CORRECTION] ✏️  Réponse {reponse_id} corrigée et en cours d'indexation dans Qdrant.")
        feedback_job.apply_async(args=[reponse_id], queue="queue_ingestion")

        return {
            "reponse_id": reponse_id,
            "statut": "CORRIGÉE",
            "contenu_corrige": payload.contenu_corrige,
            "message": "Réponse corrigée.",
        }
    finally:
        db.close()


@router.get("/reponses/en-attente")
async def lister_reponses_en_attente(domaine: str | None = None, limit: int = 20):
    """Liste les réponses en attente de validation — utile pour l'interface back-office."""
    db = SessionLocal()
    try:
        query = (
            db.query(Reponse, Ticket)
            .join(Ticket, Ticket.id == Reponse.ticket_id)
            .filter(Reponse.statut == "EN_ATTENTE")
        )

        if domaine:
            query = query.filter(Ticket.domaine == domaine.upper())

        resultats = query.order_by(Reponse.created_at.asc()).limit(limit).all()

        return [
            {
                "reponse_id": str(r.id),
                "ticket_id": str(r.ticket_id),
                "question": t.question,
                "domaine": t.domaine,
                "reponse": r.contenu,
                "source": r.source,
                "score_similarite": r.score_similarite,
                "created_at": r.created_at.isoformat(),
            }
            for r, t in resultats
        ]
    finally:
        db.close()
