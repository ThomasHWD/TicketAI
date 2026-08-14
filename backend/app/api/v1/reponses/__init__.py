from fastapi import APIRouter

from .actions import router as actions_router
from .listing import router as listing_router
from .obsolescence import router as obsolescence_router

router = APIRouter()
router.include_router(actions_router)
router.include_router(listing_router)
router.include_router(obsolescence_router)
