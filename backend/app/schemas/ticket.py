import uuid

from pydantic import BaseModel, Field


class QuestionRequest(BaseModel):
    question: str
    objet: str | None = None
    domaine: str


class SuiviRequest(BaseModel):
    question: str


class CloturerRequest(BaseModel):
    note_qualite: int | None = Field(default=None, ge=1, le=5)
    note_delai: int | None = Field(default=None, ge=1, le=5)


class AssignerRequest(BaseModel):
    assignee_id: uuid.UUID


class RecheminerRequest(BaseModel):
    nouveau_domaine: str
    raison: str = Field(..., min_length=1)
