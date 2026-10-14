import re
from collections import defaultdict
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.api.v1.articles import _is_visible
from app.config import settings
from app.database import get_db
from app.models.article import Article
from app.models.article_category import ArticleCategory
from app.models.category import Category
from app.models.source import Source
from app.schemas.report import ReportRequest
from app.services.newsletter_pdf import PdfArticle, PdfReport, PdfReportOptions, build_report_pdf, key_point_lines

router = APIRouter(prefix="/reports", tags=["Reports"], dependencies=[Depends(get_current_user)])


def _filename(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:80]
    return f"{slug or 'defence-news-report'}.pdf"


@router.post("/pdf")
def build_report(payload: ReportRequest, db: Session = Depends(get_db)) -> Response:
    """A PDF of the stories the reader selected. Stories since removed or hidden are left out."""
    requested = list(dict.fromkeys(payload.article_ids))
    by_id = {
        article.id: article
        for article in db.query(Article).filter(Article.id.in_(requested)).all()
        if _is_visible(article)
    }
    articles = [by_id[article_id] for article_id in requested if article_id in by_id]
    if not articles:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="None of the selected stories are available any more.",
        )

    if payload.order != "custom":
        articles.sort(
            key=lambda article: article.published_at or article.collected_at,
            reverse=payload.order == "newest",
        )

    source_names = dict(
        db.query(Source.id, Source.name).filter(Source.id.in_({article.source_id for article in articles})).all()
    )
    categories: dict[int, list[str]] = defaultdict(list)
    for article_id, name in (
        db.query(ArticleCategory.article_id, Category.name)
        .join(Category, Category.id == ArticleCategory.category_id)
        .filter(ArticleCategory.article_id.in_([article.id for article in articles]))
        .order_by(Category.name.asc())
    ):
        categories[article_id].append(name)

    pdf_bytes = build_report_pdf(
        PdfReport(
            title=payload.title.strip(),
            date_from=payload.date_from,
            date_to=payload.date_to,
            generated_at=datetime.now(timezone.utc),
            articles=[
                PdfArticle(
                    position=position,
                    title=article.title,
                    summary=article.summary or article.description,
                    key_points=key_point_lines(article.key_points),
                    why_it_matters=article.why_it_matters,
                    categories=categories[article.id],
                    source_name=source_names.get(article.source_id),
                    published_at=article.published_at,
                    url=article.original_url,
                    image_url=article.image_url,
                    image_credit=article.image_credit,
                )
                for position, article in enumerate(articles, start=1)
            ],
            options=PdfReportOptions(
                include_summary=payload.include_summary,
                include_dates=payload.include_dates,
                include_sources=payload.include_sources,
                include_images=payload.include_images,
                include_links=payload.include_links,
                include_key_points=payload.include_key_points,
            ),
            timezone_name=settings.news_timezone,
        )
    )
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{_filename(payload.title)}"'},
    )
