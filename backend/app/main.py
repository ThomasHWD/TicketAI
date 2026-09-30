import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api.v1 import (
    admin,
    auth,
    documents,
    faq,
    notifications,
    public,
    reponses,
    sse,
    stats,
    suggestions,
    tickets,
)
from app.config import settings
from app.database import SessionLocal
from app.middleware.maintenance import MaintenanceMiddleware
from app.services.qdrant import client as qdrant_client
from app.services.qdrant import init_collection

logger = logging.getLogger(__name__)


class _SansSondeDocker(logging.Filter):
    """The compose healthcheck hits /health every 10 s: half the access log, nothing to learn from it —
    its outcome is already the container's (un)healthy status. nginx drops its own /health lines too."""

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        return not (isinstance(args, tuple) and len(args) >= 3 and args[2] == "/health")


logging.getLogger("uvicorn.access").addFilter(_SansSondeDocker())


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_collection()
    yield


app = FastAPI(
    title="Ticket - ONaCVG",
    description="App de gestion de tickets pour ONaCVG",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept", "X-Requested-With"],
)
# Starlette empile les middlewares en LIFO : MaintenanceMiddleware s'exécute en premier.
app.add_middleware(MaintenanceMiddleware)


# /health — liveness : uvicorn répond → init_collection() est passé.
# /health/ready — readiness : vérifie Postgres et Qdrant avant de servir du trafic.
@app.get("/health", include_in_schema=False)
async def health():
    return {"status": "ok"}


# Public through nginx: the exception text (host, port, user) goes to the logs, not to whoever polls.
@app.get("/health/ready", include_in_schema=False)
async def health_ready():
    erreurs: dict[str, str] = {}

    db = SessionLocal()
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        logger.exception("readiness : Postgres injoignable")
        erreurs["postgres"] = "injoignable"
    finally:
        db.close()

    try:
        qdrant_client.get_collections()
    except Exception:
        logger.exception("readiness : Qdrant injoignable")
        erreurs["qdrant"] = "injoignable"

    if erreurs:
        return JSONResponse({"status": "degraded", "erreurs": erreurs}, status_code=503)
    return {"status": "ok"}


app.include_router(auth.router, prefix="/api/v1")
app.include_router(admin.router, prefix="/api/v1")
app.include_router(documents.router, prefix="/api/v1")
app.include_router(tickets.router, prefix="/api/v1")
app.include_router(reponses.router, prefix="/api/v1")
app.include_router(notifications.router, prefix="/api/v1")
app.include_router(sse.router, prefix="/api/v1")
app.include_router(stats.router, prefix="/api/v1/stats", tags=["stats"])
app.include_router(suggestions.router, prefix="/api/v1")
app.include_router(public.router, prefix="/api/v1")
app.include_router(faq.router, prefix="/api/v1")
