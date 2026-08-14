from fastapi import APIRouter

from .groups import router as groups_router
from .health import router as health_router
from .users import router as users_router

router = APIRouter(prefix="/admin", tags=["admin"])
router.include_router(users_router)
router.include_router(groups_router)
router.include_router(health_router)
