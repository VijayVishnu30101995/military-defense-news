import re
from datetime import date, datetime, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.article import Article
from app.models.category import Category
from app.models.newsletter import Newsletter
from app.repositories.article import ArticleRepository
from app.schemas.article import (
    ArticleCreate,
    ArticleResponse,
    DashboardResponse,
    DashboardStatistics,
    NewsletterSummary,
)


class ArticleService:
    def __init__(self, db: Session):
        self.repository = ArticleRepository(db)
        self.db = db

    @staticmethod
    def _clean_text(value: str | None) -> str:
        if value is None:
            return ""
        text = re.sub(r"<[^>]+>", " ", value)
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    @classmethod
    def build_summary(cls, title: str, description: str | None = None) -> tuple[str, str, int]:
        cleaned_title = cls._clean_text(title)
        cleaned_description = cls._clean_text(description)
        base_text = cleaned_description or cleaned_title
        if not base_text:
            return ("No summary available.", "- No key points available.", 0)

        sentences = [sentence.strip() for sentence in re.split(r"(?<=[.!?])\s+", base_text) if sentence.strip()]
        if not sentences:
            sentences = [base_text]

        summary = " ".join(sentences[:2])
        summary = cls._clean_text(summary)
        if len(summary) > 260:
            summary = summary[:257].rsplit(" ", 1)[0].rstrip() + "..."
        if not summary.endswith((".", "!", "?")):
            summary = summary + "."

        key_points: list[str] = []
        for sentence in sentences[:3]:
            cleaned = cls._clean_text(sentence).rstrip(".")
            if cleaned and cleaned not in key_points:
                key_points.append(cleaned)

        if not key_points:
            key_points = [summary]

        if len(key_points) < 3:
            fragments = [
                fragment.strip().rstrip(".")
                for fragment in re.split(r"(?<=[;:,])\s+|\s+-\s+", base_text)
                if fragment.strip()
            ]
            for fragment in fragments:
                if fragment and fragment not in key_points:
                    key_points.append(fragment)
                if len(key_points) >= 3:
                    break

        key_points_text = "\n".join(f"- {point}" for point in key_points[:3])
        confidence = min(99, max(55, int(len(summary) * 0.18 + len(key_points) * 12)))
        return summary, key_points_text, confidence

    def serialize_article(self, article: Article) -> ArticleResponse:
        categories = self.repository.get_categories(article.id)
        return ArticleResponse(
            id=article.id,
            source_id=article.source_id,
            title=article.title,
            original_url=article.original_url,
            description=article.description,
            summary=article.summary,
            key_points=article.key_points,
            ai_confidence=article.ai_confidence,
            image_url=article.image_url,
            language=article.language,
            country_id=article.country_id,
            region_id=article.region_id,
            published_at=article.published_at,
            importance_score=article.importance_score,
            reliability_score=article.reliability_score,
            processing_status=article.processing_status,
            duplicate_status=article.duplicate_status,
            categories=categories,
            created_at=article.created_at,
            updated_at=article.updated_at,
        )

    def get_all(
        self,
        *,
        country_id: int | None = None,
        region_id: int | None = None,
        source_id: int | None = None,
        page: int = 1,
        page_size: int = 25,
    ) -> list[ArticleResponse]:
        articles = self.repository.get_all(
            country_id=country_id,
            region_id=region_id,
            source_id=source_id,
            page=page,
            page_size=page_size,
        )
        return [self.serialize_article(article) for article in articles]

    def get_by_id(self, article_id: int) -> ArticleResponse | None:
        article = self.repository.get_by_id(article_id)
        if article is None:
            return None
        return self.serialize_article(article)

    def create(self, article_data: ArticleCreate) -> ArticleResponse:
        duplicate = self.repository.find_duplicate(
            source_id=article_data.source_id,
            title=article_data.title,
            original_url=article_data.original_url,
            canonical_url=article_data.canonical_url,
        )
        if duplicate is not None:
            return self.serialize_article(duplicate)

        if article_data.summary is None:
            summary, key_points, ai_confidence = self.build_summary(
                article_data.title,
                article_data.description,
            )
            article_data = article_data.model_copy(
                update={
                    "summary": summary,
                    "key_points": key_points,
                    "ai_confidence": ai_confidence,
                }
            )

        article = self.repository.create(article_data)
        return self.serialize_article(article)

    def summarize_article(self, article_id: int) -> ArticleResponse:
        article = self.db.query(Article).filter(Article.id == article_id).first()
        if article is None:
            raise ValueError("Article not found")

        summary, key_points, confidence = self.build_summary(
            article.title,
            article.description or article.content_excerpt or article.summary,
        )

        article.summary = summary
        article.key_points = key_points
        article.ai_confidence = confidence
        article.processing_status = "summarized"
        article.processed_at = datetime.now(timezone.utc)
        self.db.add(article)
        self.db.commit()
        self.db.refresh(article)
        return self.serialize_article(article)

    def get_dashboard(self) -> DashboardResponse:
        total_articles = self.repository.count()
        source_count = self.repository.source_count()
        latest_articles = self.get_all(page=1, page_size=5)
        important_articles = [
            self.serialize_article(article)
            for article in (
                self.db.query(Article)
                .filter(Article.importance_score.is_not(None))
                .order_by(Article.importance_score.desc(), Article.published_at.desc().nullslast())
                .limit(5)
                .all()
            )
        ]

        latest_news = latest_articles
        top_developments = important_articles

        newsletter_row = (
            self.db.query(Newsletter)
            .order_by(Newsletter.newsletter_date.desc())
            .first()
        )

        last_updated_at = (
            self.db.query(func.max(Article.updated_at))
            .scalar()
        )

        category_count = self.db.query(func.count(Category.id)).scalar() or 0

        dashboard = DashboardResponse(
            date=date.today().isoformat(),
            last_updated_at=last_updated_at,
            statistics=DashboardStatistics(
                total_news=total_articles,
                important_news=len(important_articles),
                categories=category_count,
            ),
            top_developments=top_developments,
            latest_news=latest_news,
            newsletter=NewsletterSummary(
                id=newsletter_row.id if newsletter_row else None,
                title=newsletter_row.title if newsletter_row else None,
                available=bool(newsletter_row),
                pdf_available=bool(newsletter_row and newsletter_row.published_at),
            ),
            total_articles=total_articles,
            source_count=source_count,
            latest_articles=latest_articles,
            important_articles=important_articles,
        )
        return dashboard
