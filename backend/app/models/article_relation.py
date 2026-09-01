from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ArticleRelation(Base):
    __tablename__ = "article_relations"

    article_id: Mapped[int] = mapped_column(
        ForeignKey("articles.id", ondelete="CASCADE"),
        primary_key=True,
    )

    related_article_id: Mapped[int] = mapped_column(
        ForeignKey("articles.id", ondelete="CASCADE"),
        primary_key=True,
    )

    relation_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
