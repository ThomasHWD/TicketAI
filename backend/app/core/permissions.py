"""Helpers de contrôle d'accès par domaine et ownership.

Deux règles distinctes :
- Lecture : l'admin voit tout ; backoffice = son domaine ; lambda = son ticket.
- Écriture : tout le monde (y compris l'admin) doit être membre du domaine cible.
"""

from fastapi import HTTPException

from app.models.ticket import Ticket
from app.models.user import User


def user_domaines(user: User) -> set[str]:
    """Ensemble des domaines auxquels appartient l'utilisateur."""
    return {g.domaine for g in user.groupes}


def check_ticket_read(ticket: Ticket, current_user: User) -> None:
    """Lecture d'un ticket.

    Admin = accès global. Backoffice = domaine du ticket. Lambda = propriétaire.
    """
    if current_user.role == "ADMIN":
        return
    if current_user.groupes:
        if ticket.user_id == current_user.id:
            return
        if ticket.domaine not in user_domaines(current_user):
            raise HTTPException(403, "Vous n'avez pas accès à ce ticket.")
        return
    if ticket.user_id != current_user.id:
        raise HTTPException(403, "Vous n'avez pas accès à ce ticket.")


def check_domain_write(domaine: str, current_user: User) -> None:
    """Action d'écriture sur un domaine.

    L'utilisateur doit être membre du domaine — sans exception pour l'admin.
    """
    if domaine not in user_domaines(current_user):
        raise HTTPException(403, f"Vous n'êtes pas membre du domaine {domaine}.")
