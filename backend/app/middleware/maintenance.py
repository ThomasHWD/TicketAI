import logging
import time

from fastapi.responses import JSONResponse
from jose import JWTError
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.core.security import decode_token
from app.database import SessionLocal
from app.models.site_config import SiteConfig

logger = logging.getLogger(__name__)

CACHE_TTL = 5.0

_cache: dict = {"active": False, "message": "", "checked_at": 0.0}

_EXEMPT_PREFIXES = (
    "/health",
    "/api/v1/auth/",
    "/api/v1/public/maintenance",
    "/api/v1/admin/health",
)


def invalidate_maintenance_cache() -> None:
    _cache["checked_at"] = 0.0


def _refresh_cache() -> None:
    db = SessionLocal()
    try:
        row = db.query(SiteConfig).filter(SiteConfig.key == "maintenance").first()
        if row is not None:
            _cache["active"] = bool(row.value.get("active", False))
            _cache["message"] = row.value.get("message", "")
        else:
            _cache["active"] = False
            _cache["message"] = ""
        _cache["checked_at"] = time.monotonic()
    except Exception:
        logger.exception("Erreur lecture maintenance en DB — cache conservé")
    finally:
        db.close()


class MaintenanceMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if any(path == p or path.startswith(p) for p in _EXEMPT_PREFIXES):
            return await call_next(request)

        if time.monotonic() - _cache["checked_at"] > CACHE_TTL:
            _refresh_cache()

        if not _cache["active"]:
            return await call_next(request)

        auth_header = request.headers.get("Authorization", "")
        token = auth_header.removeprefix("Bearer ").strip()
        if token:
            try:
                payload = decode_token(token)
                if payload.get("role") == "ADMIN":
                    return await call_next(request)
            except JWTError:
                pass

        return JSONResponse(
            status_code=503,
            content={
                "detail": "Service en maintenance",
                "message": _cache["message"],
            },
        )
