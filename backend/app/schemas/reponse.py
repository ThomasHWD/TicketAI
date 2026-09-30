from pydantic import BaseModel, Field

REPONSE_MAX = 20_000

# validator_id removed — identity is now derived from the JWT, not the request body.


class ValiderRequest(BaseModel):
    faq_visible: bool = False


class FaqVisibleRequest(BaseModel):
    faq_visible: bool


class RejeterRequest(BaseModel):
    raison: str = Field(max_length=2000)


class CorrigerRequest(BaseModel):
    contenu_corrige: str = Field(max_length=REPONSE_MAX)
    tag: str | None = None
    faq_visible: bool = False


class EditerCanoniqueRequest(BaseModel):
    contenu: str = Field(max_length=REPONSE_MAX)


class ConfirmerLotRequest(BaseModel):
    """Version-keyed bulk confirmation — a re-update creates v(n+1) so a stale v(n) must not clear flags the user"""

    doc_id: str
    version: int
