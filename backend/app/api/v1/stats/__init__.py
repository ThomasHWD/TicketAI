from fastapi import APIRouter

from app.api.v1.stats.dashboard import router as _dashboard_router
from app.api.v1.stats.groupe import router as _groupe_router

router = APIRouter()
router.include_router(_dashboard_router)
router.include_router(_groupe_router)
