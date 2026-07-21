import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from app.config import settings
from app.database import SessionLocal
from app.models.reponse import Reponse
from app.models.ticket import Ticket
from app.schemas.reponse import CorrigerRequest, RejeterRequest, ValiderRequest
from app.workers.feedback import feedback_job

router = APIRouter()

ETATS_FINAUX = {"REJETÉE", "CORRIGÉE", "CANONIQUE"}


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


def verifier_verrou(ticket: Ticket, validator_id: uuid.UUID):
    """Refuse l'écriture si le ticket est verrouillé par un autre validateur
    (bail encore actif). Un bail expiré ou absent n'empêche rien."""
    if not ticket:
        return
    now = datetime.now(timezone.utc)
    if (
        ticket.locked_by
        and ticket.locked_by != validator_id
        and ticket.lock_expires_at
        and ticket.lock_expires_at > now
    ):
        raise HTTPException(409, "Ticket verrouillé par un autre validateur.")


def liberer_verrou(ticket: Ticket):
    """Libère le verrou après une transition terminale du ticket."""
    if ticket:
        ticket.locked_by = None
        ticket.locked_at = None
        ticket.lock_expires_at = None


@router.post("/reponses/{reponse_id}/valider")
async def valider_reponse(reponse_id: str, payload: ValiderRequest):
    db = SessionLocal()
    try:
        reponse = get_reponse_or_404(db, reponse_id)
        verifier_etat_initial(reponse)

        ticket = db.query(Ticket).filter(Ticket.id == reponse.ticket_id).first()
        verifier_auto_validation(reponse, payload.validator_id, ticket)
        verifier_verrou(ticket, payload.validator_id)

        # Transition EN_ATTENTE → VALIDÉE
        reponse.statut = "VALIDÉE"
        reponse.validator_id = payload.validator_id
        reponse.validated_at = datetime.now(timezone.utc)

        if ticket:
            ticket.statut_ticket = "VALIDÉ"
            liberer_verrou(ticket)

        reponse_source = None

        # Increment the number of validations
        if reponse.reponse_source_id:
            # Incrémenter sur la réponse SOURCE, pas sur la réponse courante
            reponse_source = db.query(Reponse).filter(
                Reponse.id == reponse.reponse_source_id
            ).first()
            if reponse_source:
                reponse_source.nb_validations += 1
                if reponse_source.nb_validations >= settings.seuil_canonique:
                    reponse_source.canonique = True
        else:
            # Pas de source → c'est une réponse LLM originale
            reponse.nb_validations += 1
            if reponse.nb_validations >= settings.seuil_canonique:
                reponse.canonique = True

        db.commit()

        # Feedback job : réindexe la réponse validée dans Qdrant dès la 1re validation
        # (et pas seulement une fois canonique) pour qu'elle soit retrouvable comme
        # SUGGESTION sur des questions similaires. Réindexe la réponse SOURCE si la
        # réponse courante est une copie de suggestion, sinon la réponse elle-même.
        if reponse.reponse_source_id and reponse_source:
            feedback_job.apply_async(args=[str(reponse_source.id)], queue="queue_ingestion")
        elif not reponse.reponse_source_id:
            feedback_job.apply_async(args=[reponse_id], queue="queue_ingestion")

        return {
            "reponse_id": reponse_id,
            "statut": "VALIDÉE",
            "nb_validations": reponse.nb_validations,
            "canonique": reponse.canonique,
            "validated_at": reponse.validated_at.isoformat(),
            "message": (
                "Réponse validée et indexée comme canonique."
                if reponse.canonique
                else "Réponse validée."
            ),
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
        verifier_verrou(ticket, payload.validator_id)

        # Transition EN_ATTENTE → REJETÉE
        reponse.statut = "REJETÉE"
        reponse.validator_id = payload.validator_id
        reponse.validated_at = datetime.now(timezone.utc)

        if ticket:
            ticket.statut_ticket = "REJETÉ"
            liberer_verrou(ticket)

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
        verifier_verrou(ticket, payload.validator_id)

        # Transition EN_ATTENTE → CORRIGÉE
        reponse.statut = "CORRIGÉE"
        reponse.contenu_corrige = payload.contenu_corrige
        reponse.validator_id = payload.validator_id
        reponse.validated_at = datetime.now(timezone.utc)

        if ticket:
            ticket.statut_ticket = "VALIDÉ"
            liberer_verrou(ticket)

        db.commit()

        # Feedback job to reindex the validated response in Qdrant
        print(
            f"[CORRECTION] ✏️  Réponse {reponse_id} corrigée et en cours d'indexation dans Qdrant."
        )
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
