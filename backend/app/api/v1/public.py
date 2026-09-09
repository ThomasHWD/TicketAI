from fastapi import APIRouter
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.site_config import SiteConfig
from app.services.admin_service import _CONFIG_DEFAULTS

router = APIRouter()


@router.get("/public/maintenance")
def get_maintenance_public():
    """Retourne le statut de maintenance sans authentification."""
    default = dict(_CONFIG_DEFAULTS["maintenance"])
    db: Session = SessionLocal()
    try:
        row = db.query(SiteConfig).filter(SiteConfig.key == "maintenance").first()
        if row is not None:
            return row.value
        return default
    except Exception:
        return default
    finally:
        db.close()
