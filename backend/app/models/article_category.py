from sqlalchemy import ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ArticleCategory(Base):
    __tablename__ = "article_categories"

    article_id: Mapped[int] = mapped_column(
        ForeignKey("articles.id", ondelete="CASCADE"),
        primary_key=True,
    )

    category_id: Mapped[int] = mapped_column(
        ForeignKey("categories.id", ondelete="CASCADE"),
        primary_key=True,
    )

    # 0 is the best-matching category for the article. Cards show only the first one,
    # so without this the display order falls back to the alphabet and a story about
    # frigates gets labelled "Geopolitics" because G sorts before N.
    position: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
