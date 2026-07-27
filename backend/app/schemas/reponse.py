from pydantic import BaseModel

# L'identité du validateur n'est plus transmise dans le corps de la requête :
# elle est dérivée du JWT (voir get_current_user). Les champs validator_id ont
# donc été retirés de ces schémas.


class RejeterRequest(BaseModel):
    raison: str | None = None


class CorrigerRequest(BaseModel):
    contenu_corrige: str


class EditerCanoniqueRequest(BaseModel):
    contenu: str
