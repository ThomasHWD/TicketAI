import uuid
from datetime import datetime, timezone

from app.core.permissions import check_domain_write
from app.models.notification import Notification
from app.models.reponse import Reponse
from app.models.ticket import Ticket
from fastapi import HTTPException

ETATS_FINAUX = {"VALIDÉE", "REJETÉE", "CORRIGÉE"}


def notifier_employe(
    db,
    ticket: Ticket,
    reponse_id: str,
    validator_id: uuid.UUID,
    type: str = "REPONSE_VALIDEE",
) -> None:
    """Crée une notification pour l'employé propriétaire du ticket, sauf auto-validation."""
    if not ticket or not ticket.user_id:
        return
    if ticket.user_id == validator_id:
        return
    db.add(
        Notification(
            user_id=ticket.user_id,
            ticket_id=ticket.id,
            reponse_id=uuid.UUID(reponse_id),
            type=type,
        )
    )


def get_reponse_or_404(db, reponse_id: str) -> Reponse:
    reponse = db.query(Reponse).filter(Reponse.id == uuid.UUID(reponse_id)).first()
    if not reponse:
        raise HTTPException(404, f"Réponse {reponse_id} introuvable")
    return reponse


def check_reponse_write(db, reponse: Reponse, current_user) -> None:
    """Droit d'agir sur une réponse enregistrée : le domaine du ticket qui l'a produite."""
    ticket = db.query(Ticket).filter(Ticket.id == reponse.ticket_id).first()
    if ticket is None:
        raise HTTPException(409, "Réponse sans ticket : aucun domaine ne s'y rattache.")
    check_domain_write(ticket.domaine, current_user)


def verifier_etat_initial(reponse: Reponse) -> None:
    if reponse.statut in ETATS_FINAUX:
        raise HTTPException(
            409,
            f"Réponse déjà traitée (statut={reponse.statut}). Seules les réponses EN_ATTENTE peuvent être traitées.",
        )
    if reponse.obsolete:
        # withdrawn draft (source contradicted, document removed) — validating it would serve a judged-false answer
        raise HTTPException(409, "Réponse retirée du service : elle ne peut plus être traitée.")


def verifier_auto_validation(reponse: Reponse, validator_id: uuid.UUID, ticket: Ticket) -> None:
    if ticket and ticket.user_id and ticket.user_id == validator_id:
        raise HTTPException(403, "Un validateur ne peut pas traiter ses propres tickets.")


def verifier_verrou(ticket: Ticket, validator_id: uuid.UUID) -> None:
    """Refuse l'écriture si le ticket est assigné à quelqu'un d'autre, ou verrouillé par un autre validateur (bail"""
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


def liberer_verrou(ticket: Ticket) -> None:
    """Libère le verrou après une transition terminale du ticket."""
    if ticket:
        ticket.locked_by = None
        ticket.locked_at = None
        ticket.lock_expires_at = None


def domaine_autorise(db, reponse: Reponse, current_user) -> bool:
    """`check_reponse_write` en forme booléenne, pour les traitements en lot."""
    try:
        check_reponse_write(db, reponse, current_user)
    except HTTPException:
        return False
    return True


def changements_allegees(changements: dict | None) -> dict | None:
    """Le diff de la version, sans les unités intégrales (trop volumineuses pour l'affichage)."""
    if not changements:
        return changements
    return {k: v for k, v in changements.items() if k != "unites"}
