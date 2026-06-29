from fastapi import FastAPI
from app.api.v1 import documents

app = FastAPI(
    title="TicketAI",
    description="API de gestion de tickets grâce à l'IA",
    version="0.1.0",
)

app.include_router(documents.router, prefix="/api/v1")