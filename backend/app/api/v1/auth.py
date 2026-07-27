"""Router d'authentification : login LDAP → JWT, et profil courant.

Le provisioning est « juste-à-temps » (JIT) : au premier login réussi, l'utilisateur
est créé en base à partir des attributs de l'annuaire, avec le rôle ``USER`` par
défaut. Les rôles supérieurs (VALIDATEUR/ADMIN) sont attribués manuellement en base.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.core.security import CurrentUser, create_access_token
from app.database import SessionLocal
from app.models.user import User
from app.services import ldap_auth
from app.services.ldap_auth import LdapIdentity

router = APIRouter()


def get_or_create_user(db: Session, identity: LdapIdentity) -> User:
    """Upsert l'utilisateur d'après l'annuaire (clé = email). Rôle USER par défaut."""
    user = db.query(User).filter(User.email == identity.email).first()
    if user is None:
        user = User(
            email=identity.email,
            prenom=identity.prenom,
            nom=identity.nom,
            role="USER",
        )
        db.add(user)
    else:
        # Rafraîchit prénom/nom depuis l'annuaire à chaque connexion.
        user.prenom = identity.prenom
        user.nom = identity.nom
    db.commit()
    db.refresh(user)
    return user


def _serialize_user(user: User) -> dict:
    return {
        "id": str(user.id),
        "email": user.email,
        "prenom": user.prenom,
        "nom": user.nom,
        "role": user.role,
    }


@router.post("/auth/login")
async def login(form: Annotated[OAuth2PasswordRequestForm, Depends()]):
    """Authentifie via LDAP/AD puis renvoie un JWT et le profil utilisateur."""
    identity = ldap_auth.authenticate(form.username, form.password)
    if identity is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Identifiant ou mot de passe incorrect.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    db = SessionLocal()
    try:
        user = get_or_create_user(db, identity)
        token = create_access_token(user.id, user.role)
        return {
            "access_token": token,
            "token_type": "bearer",
            "user": _serialize_user(user),
        }
    finally:
        db.close()


@router.get("/auth/me")
async def me(current_user: CurrentUser):
    """Renvoie le profil de l'utilisateur connecté."""
    return _serialize_user(current_user)
