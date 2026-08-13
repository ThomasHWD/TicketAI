from fastapi import APIRouter

from app.api.v1.stats.dashboard import router as _dashboard_router
from app.api.v1.stats.groupe import router as _groupe_router
from app.api.v1.stats.hors_domaine import router as _hors_domaine_router

router = APIRouter()
router.include_router(_dashboard_router)
router.include_router(_groupe_router)
router.include_router(_hors_domaine_router)
