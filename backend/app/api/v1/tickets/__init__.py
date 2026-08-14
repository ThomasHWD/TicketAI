from fastapi import APIRouter

from .manage import router as manage_router
from .submit import router as submit_router

router = APIRouter()
router.include_router(submit_router)
router.include_router(manage_router)
