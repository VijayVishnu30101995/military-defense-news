from sqlalchemy import ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class NewsletterArticle(Base):
    __tablename__ = "newsletter_articles"

    newsletter_id: Mapped[int] = mapped_column(
        ForeignKey("newsletters.id", ondelete="CASCADE"),
        primary_key=True,
    )

    article_id: Mapped[int] = mapped_column(
        ForeignKey("articles.id", ondelete="CASCADE"),
        primary_key=True,
    )

    position: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
