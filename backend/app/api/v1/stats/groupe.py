from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, select

from app.api.v1.stats._helpers import _get_period_bounds
from app.core.security import CurrentUser
from app.database import SessionLocal
from app.models.document_upload import DocumentUpload
from app.models.groupe import Groupe, user_groups
from app.models.reponse import Reponse
from app.models.ticket import Ticket
from app.models.user import User

router = APIRouter()


@router.get("/groupe/{groupe_id}/membres")
def get_groupe_membres_stats(
    groupe_id: UUID,
    current_user: CurrentUser,
    periode: str = Query(default="semaine", pattern="^(semaine|mois|annee)$"),
):
    """Statistiques par membre d'un groupe — accessible au chef du groupe ou à un admin."""
    db = SessionLocal()
    try:
        groupe = db.query(Groupe).filter(Groupe.id == groupe_id).first()
        if not groupe:
            raise HTTPException(404, "Groupe introuvable")

        # Vérification d'accès : admin ou chef du groupe
        if current_user.role != "ADMIN":
            is_chef = db.execute(
                select(user_groups.c.is_chef).where(
                    user_groups.c.groupe_id == groupe_id,
                    user_groups.c.user_id == current_user.id,
                    user_groups.c.is_chef.is_(True),
                )
            ).first()
            if not is_chef:
                raise HTTPException(403, "Accès réservé au chef du groupe")

        now = datetime.now(timezone.utc)
        curr_start, curr_end, _, _ = _get_period_bounds(periode, now)

        rows = db.execute(
            select(User, user_groups.c.is_chef)
            .join(user_groups, User.id == user_groups.c.user_id)
            .where(user_groups.c.groupe_id == groupe_id)
            .order_by(user_groups.c.is_chef.desc(), User.nom, User.prenom)
        ).all()

        membres = []
        for user, is_chef_flag in rows:
            nb_reponses = (
                db.query(func.count(Reponse.id))
                .join(Ticket, Reponse.ticket_id == Ticket.id)
                .filter(
                    Reponse.validator_id == user.id,
                    Reponse.statut.in_(["VALIDÉE", "CORRIGÉE"]),
                    Ticket.domaine == groupe.domaine,
                    Reponse.validated_at >= curr_start,
                    Reponse.validated_at < curr_end,
                )
                .scalar() or 0
            )

            nb_documents = (
                db.query(func.count(DocumentUpload.id))
                .filter(
                    DocumentUpload.user_id == user.id,
                    DocumentUpload.domaine == groupe.domaine,
                    DocumentUpload.created_at >= curr_start,
                    DocumentUpload.created_at < curr_end,
                )
                .scalar() or 0
            )

            membres.append({
                "id": str(user.id),
                "email": user.email,
                "prenom": user.prenom,
                "nom": user.nom,
                "is_chef": is_chef_flag,
                "nb_reponses_validees": nb_reponses,
                "nb_documents": nb_documents,
            })

        return {
            "groupe": {"id": str(groupe.id), "nom": groupe.nom, "domaine": groupe.domaine},
            "membres": membres,
        }
    finally:
        db.close()
