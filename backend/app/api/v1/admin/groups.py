from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import AdminUser
from app.database import SessionLocal
from app.models.groupe import Groupe
from app.schemas.admin import GroupeCreate
from app.services.admin_service import serialize_groupe
from app.services.broadcast import broadcast_sync

router = APIRouter()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


DB = Annotated[Session, Depends(get_db)]


@router.get("/groupes")
def list_groupes(_: AdminUser, db: DB):
    """Liste tous les groupes avec leur nombre de membres."""
    groupes = db.query(Groupe).order_by(Groupe.domaine, Groupe.nom).all()
    return [serialize_groupe(g, include_membres=True, db_session=db) for g in groupes]


@router.get("/domaines")
def list_domaines(_: AdminUser, db: DB):
    """Liste les domaines existants (valeurs distinctes sur les groupes)."""
    rows = db.query(Groupe.domaine).distinct().order_by(Groupe.domaine).all()
    return [r[0] for r in rows]


@router.post("/groupes", status_code=status.HTTP_201_CREATED)
def create_groupe(body: GroupeCreate, _: AdminUser, db: DB):
    """Crée un groupe."""
    domaine = body.domaine.strip().upper()
    if not domaine:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Le domaine est obligatoire.")
    groupe = Groupe(nom=body.nom, domaine=domaine)
    db.add(groupe)
    try:
        db.commit()
    except IntegrityError as err:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Un groupe existe déjà pour le domaine {domaine}.",
        ) from err
    db.refresh(groupe)
    broadcast_sync("sse:admin", "group_updated", {})
    return serialize_groupe(groupe, include_membres=True, db_session=db)


@router.delete("/groupes/{groupe_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_groupe(groupe_id: UUID, _: AdminUser, db: DB):
    """Supprime un groupe et ses associations membres."""
    groupe = db.query(Groupe).filter(Groupe.id == groupe_id).first()
    if groupe is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Groupe introuvable.")
    db.delete(groupe)
    db.commit()
    broadcast_sync("sse:admin", "group_updated", {})
