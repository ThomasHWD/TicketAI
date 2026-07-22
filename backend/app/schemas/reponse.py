from uuid import UUID

from pydantic import BaseModel


class ValiderRequest(BaseModel):
    validator_id: UUID

class RejeterRequest(BaseModel):
    validator_id: UUID
    raison: str | None = None

class CorrigerRequest(BaseModel):
    validator_id: UUID
    contenu_corrige: str

class EditerCanoniqueRequest(BaseModel):
    contenu: str
