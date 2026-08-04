import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from app.config import settings
from app.core.security import AdminUser, CurrentUser
from app.database import SessionLocal
from app.models.notification import Notification
from app.models.reponse import Reponse
from app.models.reponse_chunk import ReponseChunk
from app.models.ticket import Ticket
from app.schemas.reponse import (
    CorrigerRequest,
    EditerCanoniqueRequest,
    RejeterRequest,
)
from app.services.broadcast import broadcast_async
from app.services.qdrant import delete_response_point
from app.workers.feedback import feedback_job

router = APIRouter()


def _notifier_employe(db, ticket: Ticket, reponse_id: str, validator_id: uuid.UUID) -> None:
    """Crée une notification pour l'employé propriétaire du ticket, sauf auto-validation."""
    if not ticket or not ticket.user_id:
        return
    if ticket.user_id == validator_id:
        return
    db.add(Notification(
        user_id=ticket.user_id,
        ticket_id=ticket.id,
        reponse_id=uuid.UUID(reponse_id),
        type="REPONSE_VALIDEE",
    ))

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
            f"Réponse déjà traitée (statut={reponse.statut}). Seules les réponses EN_ATTENTE peuvent être traitées.",
        )


def verifier_auto_validation(reponse: Reponse, validator_id: uuid.UUID, ticket: Ticket):
    if ticket and ticket.user_id and ticket.user_id == validator_id:
        raise HTTPException(403, "Un validateur ne peut pas traiter ses propres tickets.")


def verifier_verrou(ticket: Ticket, validator_id: uuid.UUID):
    """Refuse l'écriture si le ticket est assigné à quelqu'un d'autre,
    ou verrouillé par un autre validateur (bail encore actif)."""
    if not ticket:
        return
    if ticket.assigned_to and ticket.assigned_to != validator_id:
        raise HTTPException(403, "Ce ticket est assigné à un autre validateur.")
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
async def valider_reponse(reponse_id: str, current_user: CurrentUser):
    db = SessionLocal()
    try:
        reponse = get_reponse_or_404(db, reponse_id)
        verifier_etat_initial(reponse)

        ticket = db.query(Ticket).filter(Ticket.id == reponse.ticket_id).first()
        verifier_auto_validation(reponse, current_user.id, ticket)
        verifier_verrou(ticket, current_user.id)

        # Transition EN_ATTENTE → VALIDÉE
        reponse.statut = "VALIDÉE"
        reponse.validator_id = current_user.id
        reponse.validated_at = datetime.now(timezone.utc)

        if ticket:
            ticket.statut_ticket = "VALIDÉ"
            liberer_verrou(ticket)

        reponse_source = None

        # Increment the number of validations
        if reponse.reponse_source_id:
            # Incrémenter sur la réponse SOURCE, pas sur la réponse courante
            reponse_source = db.query(Reponse).filter(Reponse.id == reponse.reponse_source_id).first()
            if reponse_source:
                reponse_source.nb_validations += 1
                if reponse_source.nb_validations >= settings.seuil_canonique:
                    reponse_source.canonique = True
        else:
            # Pas de source → c'est une réponse LLM originale
            reponse.nb_validations += 1
            if reponse.nb_validations >= settings.seuil_canonique:
                reponse.canonique = True

        _notifier_employe(db, ticket, reponse_id, current_user.id)
        db.commit()

        # Feedback job : réindexe la réponse validée dans Qdrant dès la 1re validation
        # (et pas seulement une fois canonique) pour qu'elle soit retrouvable comme
        # SUGGESTION sur des questions similaires. Réindexe la réponse SOURCE si la
        # réponse courante est une copie de suggestion, sinon la réponse elle-même.
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
async def rejeter_reponse(
    reponse_id: str,
    payload: RejeterRequest,
    current_user: CurrentUser,
):
    db = SessionLocal()
    try:
        reponse = get_reponse_or_404(db, reponse_id)
        verifier_etat_initial(reponse)

        ticket = db.query(Ticket).filter(Ticket.id == reponse.ticket_id).first()
        verifier_auto_validation(reponse, current_user.id, ticket)
        verifier_verrou(ticket, current_user.id)

        # Transition EN_ATTENTE → REJETÉE
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
async def corriger_reponse(
    reponse_id: str,
    payload: CorrigerRequest,
    current_user: CurrentUser,
):
    db = SessionLocal()
    try:
        reponse = get_reponse_or_404(db, reponse_id)
        verifier_etat_initial(reponse)

        if not payload.contenu_corrige.strip():
            raise HTTPException(400, "Le contenu corrigé ne peut pas être vide.")

        ticket = db.query(Ticket).filter(Ticket.id == reponse.ticket_id).first()
        verifier_auto_validation(reponse, current_user.id, ticket)
        verifier_verrou(ticket, current_user.id)

        # Transition EN_ATTENTE → CORRIGÉE
        reponse.statut = "CORRIGÉE"
        reponse.contenu_corrige = payload.contenu_corrige
        reponse.validator_id = current_user.id
        reponse.validated_at = datetime.now(timezone.utc)

        if ticket:
            ticket.statut_ticket = "VALIDÉ"
            liberer_verrou(ticket)

        _notifier_employe(db, ticket, reponse_id, current_user.id)
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


@router.get("/reponses/en-attente")
async def lister_reponses_en_attente(
    current_user: CurrentUser,
    domaine: str | None = None,
    limit: int = 20,
):
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


@router.get("/reponses/canoniques")
async def lister_reponses_canoniques(
    current_user: CurrentUser,
    domaine: str | None = None,
    page: int = 1,
    limit: int = 20,
):
    """Liste paginée des réponses canoniques — une entrée par réponse canonique.

    On ne retourne que les réponses **sources** (`reponse_source_id IS NULL`) : chaque
    question ré-servie via la branche CANONIQUE crée une copie (`canonique=True` mais
    `reponse_source_id` renseigné) qu'il ne faut pas afficher, sinon la même réponse
    apparaîtrait autant de fois qu'elle a été réutilisée. `Ticket.occurence` porte le
    nombre de réutilisations. Sert la page de gestion « Réponses Enregistrées »."""
    db = SessionLocal()
    try:
        query = (
            db.query(Reponse, Ticket)
            .join(Ticket, Ticket.id == Reponse.ticket_id)
            .filter(Reponse.canonique.is_(True))
            .filter(Reponse.reponse_source_id.is_(None))
        )

        if domaine:
            query = query.filter(Ticket.domaine == domaine.upper())

        total = query.count()
        resultats = (
            query.order_by(Reponse.validated_at.desc().nullslast()).offset((page - 1) * limit).limit(limit).all()
        )

        return {
            "total": total,
            "page": page,
            "limit": limit,
            "items": [
                {
                    "reponse_id": str(r.id),
                    "ticket_id": str(r.ticket_id),
                    # Une réponse issue d'un tour de suivi porte sa propre question
                    # (la précision) : on l'affiche à la place de la question initiale
                    # du ticket, cohérent avec ce qui est indexé dans Qdrant.
                    "question": r.question_suivi or t.question,
                    "domaine": t.domaine,
                    "contenu": r.contenu,
                    "contenu_corrige": r.contenu_corrige,
                    "nb_validations": r.nb_validations,
                    "occurence": t.occurence,
                    "validated_at": r.validated_at.isoformat() if r.validated_at else None,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
                for r, t in resultats
            ],
        }
    finally:
        db.close()


@router.put("/reponses/{reponse_id}/editer")
async def editer_reponse_canonique(
    reponse_id: str,
    payload: EditerCanoniqueRequest,
    current_user: AdminUser,
):
    """Édite le contenu servi d'une réponse canonique puis la réindexe dans Qdrant,
    afin que les futures questions renvoient le nouveau texte. Le nouveau contenu est
    stocké dans `contenu_corrige` (champ privilégié par le feedback_job)."""
    db = SessionLocal()
    try:
        reponse = get_reponse_or_404(db, reponse_id)

        if not reponse.canonique:
            raise HTTPException(409, "Seules les réponses canoniques peuvent être éditées ici.")

        if not payload.contenu.strip():
            raise HTTPException(400, "Le contenu ne peut pas être vide.")

        reponse.contenu_corrige = payload.contenu
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
async def supprimer_reponse_canonique(reponse_id: str, current_user: AdminUser):
    """Supprime définitivement une réponse canonique : retrait du point Qdrant et de
    la ligne en base. Les futures questions similaires repassent par le pipeline RAG
    normal. Aucune cascade n'étant déclarée sur les FK, on nettoie manuellement les
    chunks liés et on détache les copies (réutilisations CANONIQUE) avant la suppression."""
    db = SessionLocal()
    try:
        reponse = get_reponse_or_404(db, reponse_id)

        if not reponse.canonique:
            raise HTTPException(409, "Seules les réponses canoniques peuvent être supprimées ici.")

        # 1. Retrait du point Qdrant (plus de match CANONIQUE/SUGGESTION).
        delete_response_point(reponse_id)

        # 2. Chunks liés (pas de cascade en base).
        db.query(ReponseChunk).filter(ReponseChunk.reponse_id == reponse.id).delete(synchronize_session=False)

        # 3. Détacher les copies (réutilisations) qui pointent sur cette source.
        #    On retire aussi leur flag `canonique` : sinon, une fois orphelines
        #    (reponse_source_id NULL), elles réapparaîtraient comme des sources
        #    dans la liste des réponses canoniques.
        db.query(Reponse).filter(Reponse.reponse_source_id == reponse.id).update(
            {"reponse_source_id": None, "canonique": False},
            synchronize_session=False,
        )

        # 4. Suppression de la réponse elle-même.
        db.delete(reponse)
        db.commit()
    finally:
        db.close()

    await broadcast_async("sse:admin", "saved_answers_updated", {"reponse_id": reponse_id})
    return {
        "reponse_id": reponse_id,
        "message": "Réponse canonique supprimée.",
    }
