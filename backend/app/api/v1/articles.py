from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, require_admin
from app.core.content_filters import is_off_topic_story
from app.database import get_db
from app.models.article import Article
from app.models.article_category import ArticleCategory
from app.models.category import Category
from app.models.country import Country
from app.models.newsletter import Newsletter
from app.models.newsletter_article import NewsletterArticle
from app.models.region import Region
from app.models.source import Source
from app.services.feed_text import split_paragraphs
from app.services.newsletter_pdf import PdfArticle, PdfNewsletter, PdfRelated, build_newsletter_pdf

router = APIRouter(
    prefix="",
    tags=["Articles"],
    dependencies=[Depends(get_current_user)],
)


def _serialize_article(db: Session, article: Article) -> dict:
    categories = (
        db.query(Category.name)
        .join(ArticleCategory, ArticleCategory.category_id == Category.id)
        .filter(ArticleCategory.article_id == article.id)
        .order_by(Category.name.asc())
        .all()
    )

    return {
        "id": article.id,
        "source_id": article.source_id,
        "title": article.title,
        "summary": article.summary,
        "description": article.description,
        "content_excerpt": article.content_excerpt,
        "image_url": article.image_url,
        "original_url": article.original_url,
        "canonical_url": article.canonical_url,
        "author": article.author,
        "language": article.language,
        "country_id": article.country_id,
        "region_id": article.region_id,
        "published_at": article.published_at.isoformat() if article.published_at else None,
        "collected_at": article.collected_at.isoformat() if article.collected_at else None,
        "importance_score": article.importance_score,
        "reliability_score": article.reliability_score,
        "key_points": article.key_points,
        "categories": [name for (name,) in categories],
        "processing_status": article.processing_status,
        "duplicate_status": article.duplicate_status,
        "created_at": article.created_at.isoformat() if article.created_at else None,
        "updated_at": article.updated_at.isoformat() if article.updated_at else None,
    }


@router.get("/dashboard")
def get_dashboard(db: Session = Depends(get_db)) -> dict:
    articles = (
        db.query(Article)
        .order_by(Article.published_at.desc().nullslast(), Article.collected_at.desc())
        .all()
    )
    articles = [
        article
        for article in articles
        if not is_off_topic_story(article.title, article.summary or article.description)
    ]
    total_news = len(articles)
    important_news = sum(
        article.importance_score is not None and article.importance_score >= 80
        for article in articles
    )
    category_count = db.query(Category.id).count()
    source_count = db.query(Source.id).count()

    top_developments = sorted(
        articles,
        key=lambda article: (
            article.importance_score is not None,
            article.importance_score or 0,
            article.published_at or article.collected_at,
        ),
        reverse=True,
    )[:4]
    latest_news = articles[:6]

    latest_newsletter = db.query(Newsletter).order_by(Newsletter.newsletter_date.desc()).first()
    newsletter_payload = {"available": False}
    if latest_newsletter is not None:
        newsletter_payload = {
            "available": True,
            "id": latest_newsletter.id,
            "title": latest_newsletter.title,
            "newsletter_date": latest_newsletter.newsletter_date.isoformat(),
        }

    return {
        "statistics": {
            "total_news": total_news,
            "important_news": important_news,
            "categories": category_count,
        },
        "source_count": source_count,
        "top_developments": [_serialize_article(db, article) for article in top_developments],
        "latest_news": [_serialize_article(db, article) for article in latest_news],
        "newsletter": newsletter_payload,
    }


@router.get("/countries")
def list_countries(db: Session = Depends(get_db)) -> list[dict]:
    countries = db.query(Country).order_by(Country.name.asc()).all()
    return [
        {
            "id": country.id,
            "name": country.name,
            "code": country.code,
            "is_active": country.is_active,
        }
        for country in countries
    ]


@router.get("/regions")
def list_regions(db: Session = Depends(get_db)) -> list[dict]:
    regions = db.query(Region).order_by(Region.name.asc()).all()
    return [
        {
            "id": region.id,
            "name": region.name,
            "is_active": region.is_active,
        }
        for region in regions
    ]


@router.get("/categories")
def list_categories(db: Session = Depends(get_db)) -> list[dict]:
    categories = db.query(Category).order_by(Category.name.asc()).all()
    return [
        {
            "id": category.id,
            "name": category.name,
            "slug": category.slug,
            "description": category.description,
            "is_active": category.is_active,
        }
        for category in categories
    ]


@router.get("/articles")
def list_articles(db: Session = Depends(get_db)) -> list[dict]:
    items = db.query(Article).order_by(Article.published_at.desc().nullslast(), Article.collected_at.desc()).all()
    return [
        _serialize_article(db, item)
        for item in items
        if not is_off_topic_story(item.title, item.summary or item.description)
    ]


@router.get("/articles/{article_id}")
def get_article(article_id: int, db: Session = Depends(get_db)) -> dict:
    article = db.query(Article).filter(Article.id == article_id).first()
    if article is None or is_off_topic_story(article.title, article.summary or article.description):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Article not found")
    return _serialize_article(db, article)


def _related_articles(db: Session, exclude_ids: set[int], limit: int) -> list[Article]:
    """Most recent stories sharing the most categories with `exclude_ids`, topped up with the latest news."""
    category_ids = [
        category_id
        for (category_id,) in db.query(ArticleCategory.category_id)
        .filter(ArticleCategory.article_id.in_(exclude_ids))
        .distinct()
    ]
    candidates: list[Article] = []
    if category_ids:
        shared = func.count(ArticleCategory.category_id).label("shared")
        candidates = [
            article
            for article, _ in db.query(Article, shared)
            .join(ArticleCategory, ArticleCategory.article_id == Article.id)
            .filter(ArticleCategory.category_id.in_(category_ids), Article.id.notin_(exclude_ids))
            .group_by(Article.id)
            .order_by(shared.desc(), Article.published_at.desc().nullslast())
            .limit(limit * 4)
        ]
    if len(candidates) < limit * 4:
        seen = exclude_ids | {article.id for article in candidates}
        candidates += (
            db.query(Article)
            .filter(Article.id.notin_(seen))
            .order_by(Article.published_at.desc().nullslast(), Article.collected_at.desc())
            .limit(limit * 4)
            .all()
        )

    related: list[Article] = []
    seen_titles: set[str] = set()
    for article in candidates:
        if article.normalized_title in seen_titles:
            continue
        if is_off_topic_story(article.title, article.summary or article.description):
            continue
        seen_titles.add(article.normalized_title)
        related.append(article)
        if len(related) == limit:
            break
    return related


@router.get("/articles/{article_id}/related")
def get_related_articles(article_id: int, limit: int = 4, db: Session = Depends(get_db)) -> list[dict]:
    if db.query(Article.id).filter(Article.id == article_id).first() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Article not found")
    limit = max(1, min(limit, 12))
    return [_serialize_article(db, article) for article in _related_articles(db, {article_id}, limit)]


@router.get("/newsletters/{newsletter_id}")
def get_newsletter(newsletter_id: int, db: Session = Depends(get_db)) -> dict:
    newsletter = db.query(Newsletter).filter(Newsletter.id == newsletter_id).first()
    if newsletter is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Newsletter not found")

    article_rows = (
        db.query(Article)
        .join(NewsletterArticle, NewsletterArticle.article_id == Article.id)
        .filter(NewsletterArticle.newsletter_id == newsletter.id)
        .order_by(NewsletterArticle.position.asc())
        .all()
    )
    article_rows = [
        article
        for article in article_rows
        if not is_off_topic_story(article.title, article.summary or article.description)
    ]

    return {
        "id": newsletter.id,
        "title": newsletter.title,
        "newsletter_date": newsletter.newsletter_date.isoformat(),
        "intro": newsletter.intro,
        "status": newsletter.status,
        "generated_at": newsletter.generated_at.isoformat() if newsletter.generated_at else None,
        "published_at": newsletter.published_at.isoformat() if newsletter.published_at else None,
        "articles": [_serialize_article(db, article) for article in article_rows],
    }


@router.post("/newsletters/generate", dependencies=[Depends(require_admin)])
def generate_newsletter(db: Session = Depends(get_db)) -> dict:
    newsletter_date = date.today()
    newsletter = db.query(Newsletter).filter(Newsletter.newsletter_date == newsletter_date).first()
    if newsletter is None:
        article_candidates = (
            db.query(Article)
            .order_by(Article.published_at.desc().nullslast(), Article.collected_at.desc())
            .all()
        )
        recent = [
            article
            for article in article_candidates
            if not is_off_topic_story(article.title, article.summary or article.description)
        ][:40]
        # Lead with stories whose publishers syndicate the full text; sorted() is stable, so recency order holds.
        ranked = sorted(recent, key=lambda article: not article.content_excerpt)
        article_candidates = []
        per_source: dict[int, int] = {}
        for article in ranked:
            if per_source.get(article.source_id, 0) >= 2:
                continue
            per_source[article.source_id] = per_source.get(article.source_id, 0) + 1
            article_candidates.append(article)
            if len(article_candidates) == 5:
                break
        if len(article_candidates) < 5:
            article_candidates += [article for article in ranked if article not in article_candidates][: 5 - len(article_candidates)]

        newsletter = Newsletter(
            newsletter_date=newsletter_date,
            title=f"Defense Brief - {newsletter_date.isoformat()}",
            intro="Today's defense briefing highlights the key developments across the monitored theaters.",
            status="draft",
            generated_at=datetime.now(timezone.utc),
        )
        db.add(newsletter)
        db.flush()

        for position, article in enumerate(article_candidates):
            db.add(
                NewsletterArticle(
                    newsletter_id=newsletter.id,
                    article_id=article.id,
                    position=position,
                )
            )

        db.commit()
        db.refresh(newsletter)

    return get_newsletter(newsletter.id, db)


@router.get("/newsletters/{newsletter_id}/pdf")
def download_newsletter_pdf(newsletter_id: int, db: Session = Depends(get_db)) -> Response:
    newsletter = db.query(Newsletter).filter(Newsletter.id == newsletter_id).first()
    if newsletter is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Newsletter not found")

    article_rows = (
        db.query(Article)
        .join(NewsletterArticle, NewsletterArticle.article_id == Article.id)
        .filter(NewsletterArticle.newsletter_id == newsletter.id)
        .order_by(NewsletterArticle.position.asc())
        .all()
    )
    article_rows = [
        article
        for article in article_rows
        if not is_off_topic_story(article.title, article.summary or article.description)
    ]

    related_rows = _related_articles(db, {article.id for article in article_rows}, 5) if article_rows else []

    source_names = dict(
        db.query(Source.id, Source.name)
        .filter(Source.id.in_({article.source_id for article in article_rows + related_rows}))
        .all()
    )

    def category_names(article_id: int) -> list[str]:
        return [
            name
            for (name,) in db.query(Category.name)
            .join(ArticleCategory, ArticleCategory.category_id == Category.id)
            .filter(ArticleCategory.article_id == article_id)
            .order_by(Category.name.asc())
            .all()
        ]

    pdf_articles = []
    for position, article in enumerate(article_rows, start=1):
        key_points = [
            line.lstrip("-* ").strip()
            for line in (article.key_points or "").splitlines()
            if line.strip()
        ]
        pdf_articles.append(
            PdfArticle(
                position=position,
                title=article.title,
                summary=article.summary or article.description,
                body=split_paragraphs(article.content_excerpt),
                key_points=key_points,
                categories=category_names(article.id),
                source_name=source_names.get(article.source_id),
                author=article.author,
                published_at=article.published_at,
                url=article.original_url,
                image_url=article.image_url,
            )
        )

    pdf_related = [
        PdfRelated(
            title=article.title,
            source_name=source_names.get(article.source_id),
            published_at=article.published_at,
            url=article.original_url,
            categories=category_names(article.id),
        )
        for article in related_rows
    ]

    pdf_bytes = build_newsletter_pdf(
        PdfNewsletter(
            title=newsletter.title,
            newsletter_date=newsletter.newsletter_date,
            intro=newsletter.intro,
            generated_at=newsletter.generated_at,
            articles=pdf_articles,
            related=pdf_related,
            edition=newsletter.id,
        )
    )
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="defense-brief-{newsletter.newsletter_date.isoformat()}.pdf"',
        },
    )
