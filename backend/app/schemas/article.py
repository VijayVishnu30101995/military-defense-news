from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CountryResponse(BaseModel):
    id: int
    name: str
    code: str
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


class RegionResponse(BaseModel):
    id: int
    name: str
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


class CategoryResponse(BaseModel):
    id: int
    name: str
    slug: str
    description: str | None = None
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


class ArticleBase(BaseModel):
    source_id: int
    title: str
    original_url: str
    description: str | None = None
    summary: str | None = None
    key_points: str | None = None
    ai_confidence: int | None = None
    image_url: str | None = None
    language: str = "en"
    country_id: int | None = None
    region_id: int | None = None
    published_at: datetime | None = None
    importance_score: int | None = None
    relevance_score: int | None = None
    reliability_score: int | None = None
    processing_status: str = "pending"
    duplicate_status: str = "unique"
    categories: list[str] = Field(default_factory=list)


class ArticleCreate(ArticleBase):
    author: str | None = None
    canonical_url: str | None = None
    external_id: str | None = None
    content_excerpt: str | None = None
    image_url: str | None = None
    key_points: str | None = None
    ai_confidence: int | None = None


class ArticleUpdate(BaseModel):
    title: str | None = None
    original_url: str | None = None
    canonical_url: str | None = None
    description: str | None = None
    summary: str | None = None
    key_points: str | None = None
    image_url: str | None = None
    categories: list[str] | None = None
    country_id: int | None = None
    region_id: int | None = None
    published_at: datetime | None = None
    importance_score: int | None = None
    relevance_score: int | None = None
    reliability_score: int | None = None
    processing_status: str | None = None
    duplicate_status: str | None = None
    ai_confidence: int | None = None


class ArticleResponse(ArticleBase):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DashboardStatistics(BaseModel):
    total_news: int
    important_news: int
    categories: int


class NewsletterSummary(BaseModel):
    id: int | None = None
    title: str | None = None
    available: bool = False
    pdf_available: bool = False


class DashboardResponse(BaseModel):
    date: str
    last_updated_at: datetime | None = None
    statistics: DashboardStatistics
    top_developments: list[ArticleResponse] = Field(default_factory=list)
    latest_news: list[ArticleResponse] = Field(default_factory=list)
    newsletter: NewsletterSummary = Field(default_factory=NewsletterSummary)

    total_articles: int | None = None
    source_count: int | None = None
    latest_articles: list[ArticleResponse] = Field(default_factory=list)
    important_articles: list[ArticleResponse] = Field(default_factory=list)
