from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.v1 import admin, auth, documents, notifications, reponses, sse, stats, suggestions, tickets
from app.services.qdrant import init_collection


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_collection()
    yield


app = FastAPI(
    title="TicketAI",
    description="API de gestion de tickets grâce à l'IA",
    version="0.1.0",
    lifespan=lifespan,
)


# Sonde de liveness pour Docker. Uvicorn n'ouvre le port qu'après la fin du
# lifespan : un 200 ici garantit donc déjà que init_collection() est passé.
# Le diagnostic détaillé des dépendances vit dans GET /api/v1/admin/health.
@app.get("/health", include_in_schema=False)
async def health():
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
