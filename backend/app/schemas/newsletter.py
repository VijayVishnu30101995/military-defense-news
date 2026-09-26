from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class NewsletterArticleSummary(BaseModel):
    article_id: int
    position: int
    title: str
    summary: str | None = None
    source_id: int
    original_url: str | None = None


class NewsletterResponse(BaseModel):
    id: int
    newsletter_date: date
    title: str
    intro: str | None = None
    status: str
    generated_at: datetime | None = None
    published_at: datetime | None = None
    articles: list[NewsletterArticleSummary] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)
