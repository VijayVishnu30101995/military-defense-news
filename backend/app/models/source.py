from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(primary_key=True)

    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        unique=True,
    )

    website_url: Mapped[str] = mapped_column(
        String(2048),
        nullable=False,
    )

    feed_url: Mapped[str | None] = mapped_column(
        String(2048),
        nullable=True,
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

    source_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    language: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        default="en",
        server_default="en",
    )

    reliability_score: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=100,
        server_default="100",
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
    )

    collection_frequency: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=360,
        server_default="360",
    )

    last_success_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    last_failure_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
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
