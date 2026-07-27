"""JWT + dépendances d'authentification FastAPI.

Après validation LDAP, on émet un JWT (``sub`` = id utilisateur, claim ``role``).
Les endpoints protégés récupèrent l'utilisateur courant via ``get_current_user``,
qui décode le token et charge le ``User`` en base. L'identité fait ainsi autorité
côté serveur : elle ne provient plus du corps de la requête.
"""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt

from app.config import settings
from app.database import SessionLocal
from app.models.user import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/v1/auth/login")

_CREDENTIALS_EXC = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Identifiants invalides ou session expirée.",
    headers={"WWW-Authenticate": "Bearer"},
)


def create_access_token(user_id: uuid.UUID | str, role: str) -> str:
    """Émet un JWT signé pour l'utilisateur donné."""
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.access_token_expire_minutes
    )
    payload = {"sub": str(user_id), "role": role, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict:
    """Décode et vérifie la signature/expiration d'un JWT. Lève ``JWTError`` sinon."""
    return jwt.decode(
        token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm]
    )


def get_current_user(token: Annotated[str, Depends(oauth2_scheme)]) -> User:
    """Dépendance FastAPI : renvoie l'utilisateur authentifié ou lève 401."""
    try:
        payload = decode_token(token)
        user_id = payload.get("sub")
        if not user_id:
            raise _CREDENTIALS_EXC
        uid = uuid.UUID(user_id)
    except (JWTError, ValueError) as exc:
        raise _CREDENTIALS_EXC from exc

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == uid).first()
        if user is None:
            raise _CREDENTIALS_EXC
        return user
    finally:
        db.close()


def require_admin(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    """Réserve une route aux administrateurs."""
    if current_user.role != "ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Action réservée aux administrateurs.",
        )
    return current_user


# Alias de type réutilisables dans les routeurs (style Annotated, évite B008).
CurrentUser = Annotated[User, Depends(get_current_user)]
AdminUser = Annotated[User, Depends(require_admin)]
