"""Domain access helpers. Read: admin=all, backoffice=own domain, lambda=own ticket. Write: must be a domain member"""

from fastapi import HTTPException

from app.models.ticket import Ticket
from app.models.user import User


def user_domaines(user: User) -> set[str]:
    """Ensemble des domaines auxquels appartient l'utilisateur."""
    return {g.domaine for g in user.groupes}


def check_ticket_read(ticket: Ticket, current_user: User) -> None:
    """Read access — admin=global, backoffice=domain, lambda=owner."""
    if current_user.groupes:
        if ticket.user_id == current_user.id:
            return
        if ticket.domaine not in user_domaines(current_user):
            raise HTTPException(403, "Vous n'avez pas accès à ce ticket.")
        return
    if ticket.user_id != current_user.id:
        raise HTTPException(403, "Vous n'avez pas accès à ce ticket.")


def check_domain_read(domaine: str, current_user: User) -> None:
    """Read access to a domain resource — admin sees all, others limited to their domains."""
    if current_user.role == "ADMIN":
        return
    if domaine not in user_domaines(current_user):
        raise HTTPException(403, f"Vous n'avez pas accès au domaine {domaine}.")


def check_domain_write(domaine: str, current_user: User) -> None:
    """Write access — user must be a domain member, no admin exception."""
    if domaine not in user_domaines(current_user):
        raise HTTPException(403, f"Vous n'êtes pas membre du domaine {domaine}.")
