from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class SourceBase(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    website_url: HttpUrl
    feed_url: HttpUrl | None = None
    country_id: int | None = None
    region_id: int | None = None
    source_type: str = Field(min_length=1, max_length=50)
    language: str = Field(default="en", min_length=2, max_length=10)
    reliability_score: int = Field(default=100, ge=0, le=100)
    is_active: bool = True
    collection_frequency: int = Field(default=360, ge=1)


class SourceCreate(SourceBase):
    pass


class SourceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    website_url: HttpUrl | None = None
    feed_url: HttpUrl | None = None
    country_id: int | None = None
    region_id: int | None = None
    source_type: str | None = Field(default=None, min_length=1, max_length=50)
    language: str | None = Field(default=None, min_length=2, max_length=10)
    reliability_score: int | None = Field(default=None, ge=0, le=100)
    is_active: bool | None = None
    collection_frequency: int | None = Field(default=None, ge=1)


class SourceResponse(SourceBase):
    id: int
    last_success_at: datetime | None = None
    last_failure_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
