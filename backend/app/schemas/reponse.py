from pydantic import BaseModel

# validator_id removed — identity is now derived from the JWT, not the request body.


class ValiderRequest(BaseModel):
    faq_visible: bool = False


class FaqVisibleRequest(BaseModel):
    faq_visible: bool


class RejeterRequest(BaseModel):
    raison: str


class CorrigerRequest(BaseModel):
    contenu_corrige: str


class EditerCanoniqueRequest(BaseModel):
    contenu: str


class ConfirmerLotRequest(BaseModel):
    """Version-keyed bulk confirmation — a re-update creates v(n+1) so a stale v(n) must not clear flags the user"""

    doc_id: str
    version: int
