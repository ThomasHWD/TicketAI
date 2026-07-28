"""Gestion des utilisateurs et des groupes — réservé aux administrateurs."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import AdminUser
from app.database import SessionLocal
from app.models.groupe import Groupe, user_groups
from app.models.user import User

router = APIRouter(prefix="/admin", tags=["admin"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


DB = Annotated[Session, Depends(get_db)]


# ── Schémas ──────────────────────────────────────────────────────────


class GroupeCreate(BaseModel):
    nom: str
    domaine: str



# ── Sérialisation ────────────────────────────────────────────────────


def _serialize_groupe(g: Groupe, include_membres: bool = False, db_session=None) -> dict:
    data = {
        "id": str(g.id),
        "nom": g.nom,
        "domaine": g.domaine,
        "created_at": g.created_at.isoformat() if g.created_at else None,
        "nb_membres": len(g.membres),
    }
    if include_membres:
        chef_ids = {
            row.user_id
            for row in db_session.execute(
                user_groups.select().where(
                    user_groups.c.groupe_id == g.id,
                    user_groups.c.is_chef.is_(True),
                )
            )
        } if db_session else set()
        data["membres"] = [
            {**_serialize_user_summary(u), "is_chef": u.id in chef_ids}
            for u in g.membres
        ]
    return data


def _serialize_user_summary(u: User) -> dict:
    return {
        "id": str(u.id),
        "email": u.email,
        "prenom": u.prenom,
        "nom": u.nom,
        "role": u.role,
        "departement": u.departement,
        "is_gestionnaire": u.is_gestionnaire,
        "groupes": [{"id": str(g.id), "nom": g.nom, "domaine": g.domaine} for g in u.groupes],
    }


# ── Gestionnaires / utilisateurs ─────────────────────────────────────


@router.get("/gestionnaires")
def list_gestionnaires(_: AdminUser, db: DB):
    """Liste les utilisateurs marqués Gestionnaire dans l'AD."""
    users = (
        db.query(User)
        .filter(User.is_gestionnaire.is_(True))
        .order_by(User.nom, User.prenom)
        .all()
    )
    return [_serialize_user_summary(u) for u in users]


# ── Groupes ──────────────────────────────────────────────────────────


@router.get("/groupes")
def list_groupes(_: AdminUser, db: DB):
    """Liste tous les groupes avec leur nombre de membres."""
    groupes = db.query(Groupe).order_by(Groupe.domaine, Groupe.nom).all()
    return [_serialize_groupe(g, include_membres=True, db_session=db) for g in groupes]


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
    return _serialize_groupe(groupe, include_membres=True, db_session=db)


@router.delete("/groupes/{groupe_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_groupe(groupe_id: UUID, _: AdminUser, db: DB):
    """Supprime un groupe et ses associations membres."""
    groupe = db.query(Groupe).filter(Groupe.id == groupe_id).first()
    if groupe is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Groupe introuvable.")
    db.delete(groupe)
    db.commit()


# ── Membres ──────────────────────────────────────────────────────────


@router.post("/groupes/{groupe_id}/membres/{user_id}", status_code=status.HTTP_201_CREATED)
def add_membre(groupe_id: UUID, user_id: UUID, _: AdminUser, db: DB):
    """Ajoute un utilisateur dans un groupe."""
    groupe = db.query(Groupe).filter(Groupe.id == groupe_id).first()
    if groupe is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Groupe introuvable.")
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Utilisateur introuvable.")
    if user not in groupe.membres:
        groupe.membres.append(user)
        db.commit()
    db.refresh(groupe)
    return _serialize_groupe(groupe, include_membres=True, db_session=db)


@router.delete("/groupes/{groupe_id}/membres/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_membre(groupe_id: UUID, user_id: UUID, _: AdminUser, db: DB):
    """Retire un utilisateur d'un groupe."""
    groupe = db.query(Groupe).filter(Groupe.id == groupe_id).first()
    if groupe is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Groupe introuvable.")
    user = db.query(User).filter(User.id == user_id).first()
    if user and user in groupe.membres:
        groupe.membres.remove(user)
        db.commit()


class ChefPayload(BaseModel):
    is_chef: bool


@router.put("/groupes/{groupe_id}/membres/{user_id}/chef")
def set_chef(groupe_id: UUID, user_id: UUID, body: ChefPayload, _: AdminUser, db: DB):
    """Désigne ou retire le rôle de chef pour un membre d'un groupe."""
    groupe = db.query(Groupe).filter(Groupe.id == groupe_id).first()
    if groupe is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Groupe introuvable.")
    user = db.query(User).filter(User.id == user_id).first()
    if user is None or user not in groupe.membres:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Membre introuvable dans ce groupe.")
    db.execute(
        user_groups.update()
        .where(user_groups.c.groupe_id == groupe_id, user_groups.c.user_id == user_id)
        .values(is_chef=body.is_chef)
    )
    db.commit()
    db.refresh(groupe)
    return _serialize_groupe(groupe, include_membres=True, db_session=db)
