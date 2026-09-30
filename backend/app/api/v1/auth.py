"""Auth router — LDAP login → JWT. JIT provisioning: user created on first login with USER role; higher roles"""

import logging
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

logger = logging.getLogger(__name__)

_LOGIN_MAX_ATTEMPTS = 10
_LOGIN_WINDOW_SECONDS = 60
# Per account, failures only: the per-IP counter alone let one address spray every account, and behind a shared
# NAT it is the only brake that still tells users apart.
_LOGIN_ECHECS_PAR_COMPTE = 10
_LOGIN_ECHECS_FENETRE_SECONDES = 900


def _cle_compte(username: str) -> str:
    return f"rate:login:compte:{username.strip().lower()}"


def _trop_de_tentatives(ttl: int) -> HTTPException:
    ttl = max(ttl, 1)
    return HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail=f"Trop de tentatives de connexion. Réessayez dans {ttl} secondes.",
        headers={"Retry-After": str(ttl)},
    )


def _check_login_rate(r, ip: str, username: str) -> None:
    """10 tentatives/min par IP, 10 échecs/15 min par compte. Fail-closed : Valkey indisponible bloque le login."""
    try:
        key = f"rate:login:{ip}"
        count = r.incr(key)
        if count == 1:
            r.expire(key, _LOGIN_WINDOW_SECONDS)
        if count > _LOGIN_MAX_ATTEMPTS:
            raise _trop_de_tentatives(r.ttl(key))
        cle_compte = _cle_compte(username)
        if int(r.get(cle_compte) or 0) >= _LOGIN_ECHECS_PAR_COMPTE:
            raise _trop_de_tentatives(r.ttl(cle_compte))
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Rate limiter indisponible, login bloqué par précaution : %s", e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service temporairement indisponible, réessayez dans un instant.",
        ) from e


def _noter_resultat_login(r, username: str, *, succes: bool) -> None:
    cle = _cle_compte(username)
    try:
        if succes:
            r.delete(cle)
        else:
            r.incr(cle)
            r.expire(cle, _LOGIN_ECHECS_FENETRE_SECONDES, nx=True)
    except Exception as e:
        logger.error("Compteur d'échecs de login non mis à jour : %s", e)


router = APIRouter()


def get_or_create_user(db: Session, identity: LdapIdentity) -> User:
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
    r = redis_lib.from_url(settings.valkey_url, socket_connect_timeout=1)
    _check_login_rate(r, request.client.host if request.client else "unknown", form.username)
    identity = ldap_auth.authenticate(form.username, form.password)
    _noter_resultat_login(r, form.username, succes=identity is not None)
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
    db = SessionLocal()
    try:
        return _serialize_user(current_user, db)
    finally:
        db.close()
