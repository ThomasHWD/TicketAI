from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app.core.security import AdminUser, CurrentUser
from app.database import SessionLocal
from app.models.suggestion import Suggestion

router = APIRouter(prefix="/suggestions", tags=["suggestions"])


class SuggestionIn(BaseModel):
    contenu: str = Field(..., min_length=10, max_length=2000)


class SuggestionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    contenu: str
    lu: bool
    created_at: str
    user_email: str | None
    user_nom: str | None


@router.post("", status_code=201)
def soumettre_suggestion(body: SuggestionIn, current_user: CurrentUser):
    db = SessionLocal()
    try:
        suggestion = Suggestion(user_id=current_user.id, contenu=body.contenu)
        db.add(suggestion)
        db.commit()
        return {"ok": True}
    finally:
        db.close()


@router.get("", response_model=list[SuggestionOut])
def lister_suggestions(_admin: AdminUser):
    db = SessionLocal()
    try:
        rows = (
            db.query(Suggestion)
            .order_by(Suggestion.created_at.desc())
            .all()
        )
        return [
            SuggestionOut(
                id=str(s.id),
                contenu=s.contenu,
                lu=s.lu,
                created_at=s.created_at.isoformat(),
                user_email=s.user.email if s.user else None,
                user_nom=f"{s.user.prenom or ''} {s.user.nom or ''}".strip() if s.user else None,
            )
            for s in rows
        ]
    finally:
        db.close()


@router.delete("/{suggestion_id}", status_code=204)
def supprimer_suggestion(suggestion_id: str, _admin: AdminUser):
    db = SessionLocal()
    try:
        s = db.query(Suggestion).filter(Suggestion.id == suggestion_id).first()
        if not s:
            raise HTTPException(404, "Suggestion introuvable")
        if not s.lu:
            raise HTTPException(409, "Seules les suggestions lues peuvent être supprimées")
        db.delete(s)
        db.commit()
    finally:
        db.close()


@router.patch("/{suggestion_id}/lu")
def marquer_lu(suggestion_id: str, _admin: AdminUser):
    db = SessionLocal()
    try:
        s = db.query(Suggestion).filter(Suggestion.id == suggestion_id).first()
        if not s:
            raise HTTPException(404, "Suggestion introuvable")
        s.lu = not s.lu
        db.commit()
        return {"lu": s.lu}
    finally:
        db.close()
