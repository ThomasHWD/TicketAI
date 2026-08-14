from fastapi import APIRouter

from .core import router as core_router
from .versions import router as versions_router

router = APIRouter()
router.include_router(core_router)
router.include_router(versions_router)
