from pydantic import BaseModel


class CollectionRunResponse(BaseModel):
    source_id: int
    articles_found: int
    articles_created: int
    status: str
    message: str
    warning: str | None = None


class CollectionRunRequest(BaseModel):
    # None collects every active source with a feed; a list retries just those sources.
    source_ids: list[int] | None = None
