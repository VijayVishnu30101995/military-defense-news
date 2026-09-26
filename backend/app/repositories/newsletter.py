from datetime import date

from sqlalchemy.orm import Session

from app.models.article import Article
from app.models.newsletter import Newsletter
from app.models.newsletter_article import NewsletterArticle


class NewsletterRepository:
    def __init__(self, db: Session):
        self.db = db

    def list_all(self) -> list[Newsletter]:
        return self.db.query(Newsletter).order_by(Newsletter.newsletter_date.desc()).all()

    def get_by_id(self, newsletter_id: int) -> Newsletter | None:
        return self.db.query(Newsletter).filter(Newsletter.id == newsletter_id).first()

    def get_by_date(self, newsletter_date: date) -> Newsletter | None:
        return self.db.query(Newsletter).filter(Newsletter.newsletter_date == newsletter_date).first()

    def get_articles(self, newsletter_id: int) -> list[tuple[Article, NewsletterArticle]]:
        rows = (
            self.db.query(Article, NewsletterArticle)
            .join(NewsletterArticle, NewsletterArticle.article_id == Article.id)
            .filter(NewsletterArticle.newsletter_id == newsletter_id)
            .order_by(NewsletterArticle.position.asc())
            .all()
        )
        return rows

    def generate_for_date(self, newsletter_date: date, selected_articles: list[Article]) -> Newsletter:
        existing = self.get_by_date(newsletter_date)
        if existing is not None:
            return existing

        newsletter = Newsletter(
            newsletter_date=newsletter_date,
            title=f"Daily Defense Brief - {newsletter_date.isoformat()}",
            intro="Top defense and security developments for the day.",
            status="draft",
        )
        self.db.add(newsletter)
        self.db.commit()
        self.db.refresh(newsletter)

        for index, article in enumerate(selected_articles, start=1):
            self.db.add(
                NewsletterArticle(
                    newsletter_id=newsletter.id,
                    article_id=article.id,
                    position=index,
                )
            )

        newsletter.status = "published"
        self.db.commit()
        self.db.refresh(newsletter)
        return newsletter
