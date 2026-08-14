from fastapi import APIRouter, HTTPException

from app.core.security import BackofficeUser
from app.database import SessionLocal
from app.models.reponse import Reponse
from app.schemas.reponse import ConfirmerLotRequest
from app.services.broadcast import broadcast_async
from app.services.obsolescence import (
    confirmer_actualite,
    fermeture_copies,
)
from app.services.reponse_service import check_reponse_write, domaine_autorise, get_reponse_or_404

router = APIRouter()


@router.post("/reponses/confirmer-actualite")
async def confirmer_actualite_lot(payload: ConfirmerLotRequest, current_user: BackofficeUser):
    """Confirme en lot toutes les réponses signalées par une version de document."""
    db = SessionLocal()
    try:
        candidates = (
            db.query(Reponse)
            .filter(
                Reponse.a_relire.is_(True),
                Reponse.a_relire_doc_id == payload.doc_id,
                Reponse.a_relire_version == payload.version,
            )
            .all()
        )

        autorisees = [r for r in candidates if domaine_autorise(db, r, current_user)]
        familles = fermeture_copies(db, {r.id for r in autorisees}) if autorisees else set()
        a_lever = db.query(Reponse).filter(Reponse.id.in_(familles)).all() if familles else []
        confirmer_actualite(db, a_lever)
        nb = len(autorisees)
    finally:
        db.close()

    await broadcast_async("sse:admin", "saved_answers_updated", {"doc_id": payload.doc_id})
    return {
        "doc_id": payload.doc_id,
        "version": payload.version,
        "nb_confirmees": nb,
        "message": f"{nb} réponse(s) confirmée(s) comme toujours d'actualité.",
    }


@router.post("/reponses/{reponse_id}/confirmer-actualite")
async def confirmer_actualite_reponse(reponse_id: str, current_user: BackofficeUser):
    """Un humain a relu et juge la réponse toujours juste : le signalement tombe."""
    db = SessionLocal()
    try:
        reponse = get_reponse_or_404(db, reponse_id)
        check_reponse_write(db, reponse, current_user)

        if not reponse.a_relire:
            raise HTTPException(409, "Cette réponse n'est pas signalée à relire.")

        famille = fermeture_copies(db, {reponse.id})
        confirmer_actualite(db, db.query(Reponse).filter(Reponse.id.in_(famille)).all())
    finally:
        db.close()

    await broadcast_async("sse:admin", "saved_answers_updated", {"reponse_id": reponse_id})
    return {
        "reponse_id": reponse_id,
        "message": "Réponse confirmée comme toujours d'actualité.",
    }
