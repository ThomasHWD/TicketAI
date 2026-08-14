from pydantic import BaseModel


class ConfirmerMajRequest(BaseModel):
    staging_id: str
