from fastapi import APIRouter

from .assignment import router as assignment_router
from .detail import router as detail_router
from .listing import router as listing_router
from .locking import router as locking_router
from .submit import router as submit_router

router = APIRouter()
router.include_router(submit_router)
router.include_router(listing_router)
router.include_router(detail_router)
router.include_router(locking_router)
router.include_router(assignment_router)
