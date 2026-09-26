from pydantic import BaseModel


class CollectionRunResponse(BaseModel):
    source_id: int
    articles_found: int
    articles_created: int
    status: str
    message: str
