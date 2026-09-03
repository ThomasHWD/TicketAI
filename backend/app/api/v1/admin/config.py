from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.config import settings
from app.core.security import AdminUser, CurrentUser
from app.database import get_db
from app.models.site_config import SiteConfig
from app.schemas.admin import ConfigPayload
from app.services.admin_service import _CONFIG_DEFAULTS
from app.services.broadcast import broadcast_sync

router = APIRouter()

DB = Annotated[Session, Depends(get_db)]


@router.get("/config")
def get_config(current_user: CurrentUser, db: DB):
    """Retourne la configuration du site (tout utilisateur authentifié)."""
    rows = db.query(SiteConfig).all()
    result = dict(_CONFIG_DEFAULTS)
    for row in rows:
        result[row.key] = row.value
    result["jours_auto_cloture"] = settings.jours_auto_cloture
    return result


@router.put("/config/{key}")
def set_config(key: str, body: ConfigPayload, _: AdminUser, db: DB):
    """Met à jour une clé de configuration (admin uniquement)."""
    if key not in _CONFIG_DEFAULTS:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Clé de configuration inconnue : {key}")
    row = db.query(SiteConfig).filter(SiteConfig.key == key).first()
    if row is None:
        row = SiteConfig(key=key, value=body.value)
        db.add(row)
    else:
        row.value = body.value
    db.commit()
    db.refresh(row)
    if key == "banner":
        broadcast_sync("sse:global", "banner_updated", {})
    return {"key": row.key, "value": row.value}
