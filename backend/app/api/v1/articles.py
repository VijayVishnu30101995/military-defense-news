from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.core.content_filters import is_sports_story
from app.database import get_db
from app.models.article import Article
from app.models.article_category import ArticleCategory
from app.models.category import Category
from app.models.country import Country
from app.models.newsletter import Newsletter
from app.models.newsletter_article import NewsletterArticle
from app.models.region import Region
from app.models.source import Source

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
        if not is_sports_story(article.title, article.summary or article.description)
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
        if not is_sports_story(item.title, item.summary or item.description)
    ]


@router.get("/articles/{article_id}")
def get_article(article_id: int, db: Session = Depends(get_db)) -> dict:
    article = db.query(Article).filter(Article.id == article_id).first()
    if article is None or is_sports_story(article.title, article.summary or article.description):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Article not found")
    return _serialize_article(db, article)


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
        if not is_sports_story(article.title, article.summary or article.description)
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


@router.post("/newsletters/generate")
def generate_newsletter(db: Session = Depends(get_db)) -> dict:
    newsletter_date = date.today()
    newsletter = db.query(Newsletter).filter(Newsletter.newsletter_date == newsletter_date).first()
    if newsletter is None:
        article_candidates = (
            db.query(Article)
            .order_by(Article.published_at.desc().nullslast(), Article.collected_at.desc())
            .all()
        )
        article_candidates = [
            article
            for article in article_candidates
            if not is_sports_story(article.title, article.summary or article.description)
        ][:5]

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
        .limit(10)
        .all()
    )
    article_rows = [
        article
        for article in article_rows
        if not is_sports_story(article.title, article.summary or article.description)
    ]

    lines = [
        "BT /F1 20 Tf 72 760 Td (Defense Brief) Tj ET",
        f"BT /F1 12 Tf 72 732 Td ({newsletter.title}) Tj ET",
    ]
    y = 700
    for article in article_rows:
        title = (article.title or "Untitled").replace("(", "\\(").replace(")", "\\)")
        lines.append(f"BT /F1 11 Tf 72 {y} Td ({title}) Tj ET")
        y -= 24
        if y < 90:
            break

    pdf_text = "".join(
        [
            "%PDF-1.4\n",
            "1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n",
            "2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n",
            "3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>\nendobj\n",
            "4 0 obj\n<< /Length 200 >>\nstream\n",
            *[f"{line}\n" for line in lines],
            "endstream\nendobj\n",
            "5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n",
            "xref\n0 6\n0000000000 65535 f \n",
            "trailer\n<< /Root 1 0 R /Size 6 >>\nstartxref\n0\n%%EOF\n",
        ]
    )
    pdf_bytes = pdf_text.encode("latin-1", errors="replace")
    return Response(content=pdf_bytes, media_type="application/pdf")
