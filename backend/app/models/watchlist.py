from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


EMAIL_OFF = "off"
EMAIL_INSTANT = "instant"
EMAIL_DAILY = "daily"
EMAIL_FREQUENCIES = (EMAIL_OFF, EMAIL_INSTANT, EMAIL_DAILY)


class Watchlist(Base):
    """A reader's saved topic: stories mentioning any of its terms are flagged for them."""

    __tablename__ = "watchlists"

    id: Mapped[int] = mapped_column(primary_key=True)

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    # Words or phrases; a story matches when it mentions any of them.
    terms: Mapped[list[str]] = mapped_column(
        JSON,
        nullable=False,
    )

    # A story mentioning any of these is skipped even if it matches.
    exclude_terms: Mapped[list[str]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
    )

    email_frequency: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=EMAIL_OFF,
        server_default=EMAIL_OFF,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
    )

    # Highest article id already checked against this watchlist; only newer stories are checked.
    last_article_id: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class WatchlistMatch(Base):
    """A story that matched a watchlist, and whether the reader has seen or been emailed it."""

    __tablename__ = "watchlist_matches"
    __table_args__ = (UniqueConstraint("watchlist_id", "article_id", name="uq_watchlist_match"),)

    id: Mapped[int] = mapped_column(primary_key=True)

    watchlist_id: Mapped[int] = mapped_column(
        ForeignKey("watchlists.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    article_id: Mapped[int] = mapped_column(
        ForeignKey("articles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # The watchlist terms the story mentioned, shown as the reason it matched.
    matched_terms: Mapped[list[str]] = mapped_column(
        JSON,
        nullable=False,
    )

    matched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    seen_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Set once the match has been emailed, or when it never needs to be (matched before
    # the watchlist existed, or while its email was off).
    emailed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
