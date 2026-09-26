from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.database import get_db
from app.models.category import Category
from app.models.country import Country
from app.models.region import Region
from app.schemas.article import (
    ArticleCreate,
    ArticleResponse,
    CategoryResponse,
    CountryResponse,
    DashboardResponse,
    RegionResponse,
)
from app.services.article import ArticleService

router = APIRouter(tags=["Content"], dependencies=[Depends(get_current_user)])


@router.get("/countries", response_model=list[CountryResponse])
def list_countries(db: Session = Depends(get_db)) -> list[CountryResponse]:
    return db.query(Country).order_by(Country.name.asc()).all()


@router.get("/regions", response_model=list[RegionResponse])
def list_regions(db: Session = Depends(get_db)) -> list[RegionResponse]:
    return db.query(Region).order_by(Region.name.asc()).all()


@router.get("/categories", response_model=list[CategoryResponse])
def list_categories(db: Session = Depends(get_db)) -> list[CategoryResponse]:
    return db.query(Category).order_by(Category.name.asc()).all()


@router.get("/dashboard", response_model=DashboardResponse)
def dashboard(db: Session = Depends(get_db)) -> DashboardResponse:
    service = ArticleService(db)
    return service.get_dashboard()


@router.get("/articles", response_model=list[ArticleResponse])
def list_articles(
    db: Session = Depends(get_db),
    country_id: int | None = Query(default=None),
    region_id: int | None = Query(default=None),
    source_id: int | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
) -> list[ArticleResponse]:
    service = ArticleService(db)
    return service.get_all(
        country_id=country_id,
        region_id=region_id,
        source_id=source_id,
        page=page,
        page_size=page_size,
    )


@router.post("/articles", response_model=ArticleResponse)
def create_article(
    article_data: ArticleCreate,
    db: Session = Depends(get_db),
) -> ArticleResponse:
    service = ArticleService(db)
    return service.create(article_data)


@router.post("/articles/{article_id}/summarize", response_model=ArticleResponse)
def summarize_article_endpoint(
    article_id: int,
    db: Session = Depends(get_db),
) -> ArticleResponse:
    service = ArticleService(db)
    try:
        return service.summarize_article(article_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.get("/articles/{article_id}", response_model=ArticleResponse)
def get_article(article_id: int, db: Session = Depends(get_db)) -> ArticleResponse:
    service = ArticleService(db)
    article = service.get_by_id(article_id)
    if article is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Article not found",
        )
    return article
