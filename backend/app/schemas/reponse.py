from pydantic import BaseModel

# L'identité du validateur n'est plus transmise dans le corps de la requête :
# elle est dérivée du JWT (voir get_current_user). Les champs validator_id ont
# donc été retirés de ces schémas.


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
    """Confirme d'un coup toutes les réponses signalées par une version de document.

    La version fait partie de la clé : un document remis à jour entre-temps a
    reflagué ses réponses sur v(n+1), et une confirmation partie de l'écran de
    v(n) ne doit pas balayer un signalement que l'utilisateur n'a pas vu.
    """

    doc_id: str
    version: int
