from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Article(Base):
    __tablename__ = "articles"

    id: Mapped[int] = mapped_column(primary_key=True)

    source_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("sources.id", ondelete="CASCADE"),
        nullable=False,
    )

    external_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    title: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )

    normalized_title: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )

    original_url: Mapped[str] = mapped_column(
        String(2048),
        nullable=False,
    )

    canonical_url: Mapped[str | None] = mapped_column(
        String(2048),
        nullable=True,
    )

    author: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    content_excerpt: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    image_url: Mapped[str | None] = mapped_column(
        String(2048),
        nullable=True,
    )

    language: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        default="en",
        server_default="en",
    )

    country_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("countries.id", ondelete="SET NULL"),
        nullable=True,
    )

    region_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("regions.id", ondelete="SET NULL"),
        nullable=True,
    )

    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    collected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default="now()",
    )

    processed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    importance_score: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    reliability_score: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    summary: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    key_points: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    ai_confidence: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    processing_status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="pending",
        server_default="pending",
    )

    duplicate_status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="unique",
        server_default="unique",
    )

    content_hash: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default="now()",
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default="now()",
    )
