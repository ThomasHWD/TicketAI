import uuid

from pydantic import BaseModel, Field

# Every question goes to Albert (embedding, generation, judge) on a quota shared by the whole organisation:
# unbounded text let one account spend a day of it. Same caps as the form (NewTicket.tsx).
QUESTION_MAX = 2000


class QuestionRequest(BaseModel):
    question: str = Field(max_length=QUESTION_MAX)
    objet: str | None = Field(default=None, max_length=255)  # tickets.objet VARCHAR(255)
    domaine: str = Field(max_length=50)


class SuiviRequest(BaseModel):
    question: str = Field(max_length=QUESTION_MAX)


class CloturerRequest(BaseModel):
    note_qualite: int | None = Field(default=None, ge=1, le=5)
    note_delai: int | None = Field(default=None, ge=1, le=5)


class AssignerRequest(BaseModel):
    assignee_id: uuid.UUID


class RecheminerRequest(BaseModel):
    nouveau_domaine: str
    raison: str = Field(..., min_length=1)
