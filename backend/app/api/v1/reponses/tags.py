from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.core.permissions import user_domaines
from app.core.security import BackofficeUser
from app.database import SessionLocal
from app.models.reponse import Reponse
from app.models.ticket import Ticket

router = APIRouter()


@router.get("/tags")
async def lister_tags(
    current_user: BackofficeUser,
    domaine: str | None = None,
    canoniques: bool = False,
):
    """Tags distincts utilisés dans le domaine.

    `canoniques=true` : restreint aux réponses canoniques non obsolètes,
    pour le filtre de la page Réponses enregistrées.
    Sans ce paramètre : toutes les réponses, pour l'autocomplete d'édition.
    """
    db = SessionLocal()
    try:
        query = (
            db.query(Reponse.tag)
            .join(Ticket, Ticket.id == Reponse.ticket_id)
            .filter(Reponse.tag.isnot(None))
        )
        if canoniques:
            query = query.filter(
                Reponse.canonique.is_(True),
                Reponse.reponse_source_id.is_(None),
                Reponse.obsolete.is_(False),
            )
        if domaine:
            d = domaine.upper()
            if current_user.role != "ADMIN" and d not in user_domaines(current_user):
                return JSONResponse(content=[], headers={"Cache-Control": "no-store"})
            query = query.filter(Ticket.domaine == d)
        elif current_user.role != "ADMIN":
            query = query.filter(Ticket.domaine.in_(user_domaines(current_user)))

        rows = query.distinct().all()
        data = sorted(r.tag for r in rows if r.tag)
        return JSONResponse(content=data, headers={"Cache-Control": "no-store"})
    finally:
        db.close()


class TagPayload(BaseModel):
    tag: str | None = None


@router.patch("/reponses/{reponse_id}/tag")
async def mettre_a_jour_tag(
    reponse_id: str,
    payload: TagPayload,
    current_user: BackofficeUser,
):
    """Met à jour le tag d'une réponse (backoffice, tous statuts)."""
    db = SessionLocal()
    try:
        reponse = db.query(Reponse).filter(Reponse.id == reponse_id).first()
        if not reponse:
            raise HTTPException(status_code=404, detail="Réponse introuvable")

        ticket = db.query(Ticket).filter(Ticket.id == reponse.ticket_id).first()
        if current_user.role != "ADMIN":
            domaines = user_domaines(current_user)
            if not ticket or ticket.domaine not in domaines:
                raise HTTPException(status_code=403, detail="Accès refusé")

        tag = payload.tag.strip()[:100] if payload.tag else None
        reponse.tag = tag or None
        db.commit()
        return {"tag": reponse.tag}
    finally:
        db.close()
