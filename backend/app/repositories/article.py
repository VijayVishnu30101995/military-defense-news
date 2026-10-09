import hashlib
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.models.article import Article
from app.models.article_category import ArticleCategory
from app.models.category import Category
from app.models.source import Source
from app.schemas.article import ArticleCreate


MIN_TITLE_WORDS_FOR_MATCH = 6


class ArticleRepository:
    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def normalize_url(url: str) -> str:
        value = (url or "").strip()
        if not value:
            return ""

        parsed = urlsplit(value)
        if not parsed.scheme or not parsed.netloc:
            return value.rstrip("/")

        filtered_query = [
            (key, value)
            for key, value in parse_qsl(parsed.query, keep_blank_values=True)
            if key.lower() not in {
                "utm_source",
                "utm_medium",
                "utm_campaign",
                "utm_term",
                "utm_content",
                "utm_id",
                "fbclid",
                "gclid",
                "mc_cid",
                "mc_eid",
            }
        ]
        clean = parsed._replace(query=urlencode(filtered_query, doseq=True), fragment="")
        return urlunsplit(clean).rstrip("/")

    @staticmethod
    def normalize_title(title: str) -> str:
        # \w is Unicode-aware, so Arabic, Cyrillic and Devanagari titles keep their letters
        # instead of collapsing to "" and matching each other.
        text = title.strip().casefold()
        text = re.sub(r"[^\w\s]|_", " ", text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    @staticmethod
    def title_hash(title: str) -> str:
        normalized = ArticleRepository.normalize_title(title)
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    def find_duplicate(
        self,
        *,
        source_id: int,
        title: str,
        original_url: str,
        canonical_url: str | None,
    ) -> Article | None:
        normalized_url = self.normalize_url(original_url)
        normalized_title = self.normalize_title(title)
        candidate_urls = {original_url, normalized_url}
        if canonical_url:
            candidate_urls.add(canonical_url)
            candidate_urls.add(self.normalize_url(canonical_url))

        conditions = [
            Article.original_url.in_(sorted(candidate_urls)),
            Article.canonical_url.in_(sorted(candidate_urls)),
        ]
        # Short titles ("Morning Brief", "Bunker Talk") recur with different stories, so only
        # titles long enough to be specific count as a duplicate; URLs always do.
        if len(normalized_title.split()) >= MIN_TITLE_WORDS_FOR_MATCH:
            conditions.append(Article.normalized_title == normalized_title)

        return (
            self.db.query(Article)
            .filter(or_(*conditions))
            .order_by(Article.id.desc())
            .first()
        )

    def get_all(
        self,
        *,
        country_id: int | None = None,
        region_id: int | None = None,
        source_id: int | None = None,
        page: int = 1,
        page_size: int = 25,
    ) -> list[Article]:
        query = self.db.query(Article)

        if country_id is not None:
            query = query.filter(Article.country_id == country_id)

        if region_id is not None:
            query = query.filter(Article.region_id == region_id)

        if source_id is not None:
            query = query.filter(Article.source_id == source_id)

        return (
            query.order_by(Article.published_at.desc().nullslast(), Article.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )

    def get_by_id(self, article_id: int) -> Article | None:
        return self.db.query(Article).filter(Article.id == article_id).first()

    def get_category_names(self, article_id: int) -> list[str]:
        rows = (
            self.db.query(Category.name)
            .join(ArticleCategory, ArticleCategory.category_id == Category.id)
            .filter(ArticleCategory.article_id == article_id)
            .order_by(Category.name.asc())
            .all()
        )
        return [row[0] for row in rows]

    def get_categories(self, article_id: int) -> list[str]:
        return self.get_category_names(article_id)

    def count(self) -> int:
        return self.db.query(func.count(Article.id)).scalar() or 0

    def source_count(self) -> int:
        return self.db.query(func.count(Source.id)).scalar() or 0

    def create(self, data: ArticleCreate) -> Article:
        article = Article(
            source_id=data.source_id,
            title=data.title,
            normalized_title=self.normalize_title(data.title),
            original_url=self.normalize_url(data.original_url),
            canonical_url=self.normalize_url(data.canonical_url) if data.canonical_url else None,
            author=data.author,
            description=data.description,
            content_excerpt=data.content_excerpt,
            image_url=data.image_url,
            language=data.language,
            country_id=data.country_id,
            region_id=data.region_id,
            published_at=data.published_at,
            importance_score=data.importance_score,
            relevance_score=data.relevance_score,
            reliability_score=data.reliability_score,
            summary=data.summary,
            key_points=data.key_points,
            ai_confidence=data.ai_confidence,
            processing_status=data.processing_status,
            duplicate_status=data.duplicate_status,
            content_hash=self.title_hash(data.title),
            external_id=data.external_id,
        )
        self.db.add(article)
        self.db.commit()
        self.db.refresh(article)

        # data.categories arrives best-match-first; keep that order so cards can show
        # the most relevant label rather than the alphabetically first one.
        for position, category_name in enumerate(data.categories):
            name = category_name.strip()
            if not name:
                continue
            category = (
                self.db.query(Category)
                .filter(func.lower(Category.name) == name.lower())
                .first()
            )
            if category is None:
                slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "uncategorized"
                category = Category(name=name, slug=slug, description=name)
                self.db.add(category)
                self.db.commit()
                self.db.refresh(category)

            exists = (
                self.db.query(ArticleCategory)
                .filter_by(article_id=article.id, category_id=category.id)
                .first()
            )
            if exists is None:
                self.db.add(
                    ArticleCategory(
                        article_id=article.id,
                        category_id=category.id,
                        position=position,
                    )
                )

        self.db.commit()
        return article
