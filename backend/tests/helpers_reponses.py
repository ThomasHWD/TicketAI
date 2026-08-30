"""Helpers partagés entre les fichiers test_reponses_*.py."""

import uuid
from datetime import datetime, timezone

from app.models.reponse import Reponse
from app.models.ticket import Ticket
from app.models.user import User

API = "/api/v1"


def make_user(db, role="VALIDATEUR") -> User:
    user = User(email=f"{uuid.uuid4()}@test.local", role=role)
    db.add(user)
    db.flush()
    return user


def seed_ticket_reponse(
    db,
    *,
    statut="EN_ATTENTE",
    ticket_statut="RÉPONDU",
    user_id=None,
    reponse_source_id=None,
    canonique=False,
    nb_validations=0,
    contenu="Réponse test",
    contenu_corrige=None,
    locked_by=None,
    lock_expires_at=None,
    domaine="IT",
    question="Question test ?",
    question_suivi=None,
):
    """Crée un Ticket + sa Reponse et renvoie le couple (ticket, reponse).

    `question` / `question_suivi` sont exposés parce que le cache indexe le TEXTE
    DE LA QUESTION, pas celui de la réponse (cf. `app/workers/feedback.py:52-57`) :
    un test de réutilisation qui ne peut pas choisir la question testerait le
    cache sans pouvoir en piloter l'entrée. Défauts inchangés — aucun appelant
    existant n'est affecté.
    """
    ticket = Ticket(
        question=question,
        domaine=domaine,
        user_id=user_id,
        statut_ticket=ticket_statut,
        locked_by=locked_by,
        lock_expires_at=lock_expires_at,
    )
    db.add(ticket)
    db.flush()

    reponse = Reponse(
        ticket_id=ticket.id,
        contenu=contenu,
        statut=statut,
        source="LLM",
        nb_validations=nb_validations,
        canonique=canonique,
        reponse_source_id=reponse_source_id,
        contenu_corrige=contenu_corrige,
        question_suivi=question_suivi,
    )
    db.add(reponse)
    db.commit()
    db.refresh(ticket)
    db.refresh(reponse)
    return ticket, reponse


def rendre_obsolete(db, reponse, *, doc_id="doc-obsolete", raison="DOC_MIS_A_JOUR", version=2):
    reponse.obsolete = True
    reponse.obsolete_raison = raison
    reponse.obsolete_doc_id = doc_id
    reponse.obsolete_version = version
    reponse.obsolete_at = datetime.now(timezone.utc)
    db.commit()
    return reponse


def signaler(db, reponse, *, doc_id="doc-modifie", raison="DOC_MODIFIÉ", version=3):
    reponse.a_relire = True
    reponse.a_relire_raison = raison
    reponse.a_relire_doc_id = doc_id
    reponse.a_relire_version = version
    reponse.a_relire_at = datetime.now(timezone.utc)
    db.commit()
    return reponse
