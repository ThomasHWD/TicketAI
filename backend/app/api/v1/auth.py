"""Router d'authentification : login LDAP → JWT, et profil courant.

Le provisioning est « juste-à-temps » (JIT) : au premier login réussi, l'utilisateur
est créé en base à partir des attributs de l'annuaire, avec le rôle ``USER`` par
défaut. Les rôles supérieurs (VALIDATEUR/ADMIN) sont attribués manuellement en base.
"""

from typing import Annotated

import redis as redis_lib
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.core.security import CurrentUser, create_access_token
from app.database import SessionLocal
from app.models.groupe import user_groups
from app.models.user import User
from app.services import ldap_auth
from app.services.ldap_auth import LdapIdentity

_LOGIN_MAX_ATTEMPTS = 10
_LOGIN_WINDOW_SECONDS = 60


def _check_login_rate(ip: str) -> None:
    """Limite à 10 tentatives de login par minute et par IP. Fail-open si Valkey est indisponible."""
    try:
        r = redis_lib.from_url(settings.valkey_url, socket_connect_timeout=1)
        key = f"rate:login:{ip}"
        count = r.incr(key)
        if count == 1:
            r.expire(key, _LOGIN_WINDOW_SECONDS)
        if count > _LOGIN_MAX_ATTEMPTS:
            ttl = max(r.ttl(key), 1)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Trop de tentatives de connexion. Réessayez dans {ttl} secondes.",
                headers={"Retry-After": str(ttl)},
            )
    except HTTPException:
        raise
    except Exception:
        pass  # Valkey indisponible → on laisse passer (fail-open)

router = APIRouter()


def get_or_create_user(db: Session, identity: LdapIdentity) -> User:
    """Upsert l'utilisateur d'après l'annuaire (clé = email). Rôle USER par défaut."""
    user = db.query(User).filter(User.email == identity.email).first()
    if user is None:
        user = User(
            email=identity.email,
            prenom=identity.prenom,
            nom=identity.nom,
            departement=identity.departement,
            is_gestionnaire=identity.is_gestionnaire,
            role=identity.role,
        )
        db.add(user)
    else:
        # Rafraîchit les attributs depuis l'annuaire à chaque connexion.
        user.prenom = identity.prenom
        user.nom = identity.nom
        user.departement = identity.departement
        user.is_gestionnaire = identity.is_gestionnaire
        user.role = identity.role
    db.commit()
    db.refresh(user)
    return user


def _serialize_user(user: User, db: Session | None = None) -> dict:
    groupes = []
    for g in user.groupes:
        is_chef = False
        if db is not None:
            row = db.execute(
                select(user_groups.c.is_chef).where(
                    user_groups.c.user_id == user.id,
                    user_groups.c.groupe_id == g.id,
                )
            ).first()
            is_chef = bool(row and row[0])
        groupes.append({"id": str(g.id), "nom": g.nom, "domaine": g.domaine, "is_chef": is_chef})

    return {
        "id": str(user.id),
        "email": user.email,
        "prenom": user.prenom,
        "nom": user.nom,
        "role": user.role,
        "departement": user.departement,
        "groupes": groupes,
    }


@router.post("/auth/login")
async def login(request: Request, form: Annotated[OAuth2PasswordRequestForm, Depends()]):
    """Authentifie via LDAP/AD puis renvoie un JWT et le profil utilisateur."""
    _check_login_rate(request.client.host if request.client else "unknown")
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
            "user": _serialize_user(user, db),
        }
    finally:
        db.close()


@router.get("/auth/me")
async def me(current_user: CurrentUser):
    """Renvoie le profil de l'utilisateur connecté."""
    db = SessionLocal()
    try:
        return _serialize_user(current_user, db)
    finally:
        db.close()
