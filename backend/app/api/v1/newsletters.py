from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.database import get_db
from app.schemas.newsletter import NewsletterResponse
from app.services.newsletter import NewsletterService

router = APIRouter(prefix="/newsletters", tags=["Newsletters"], dependencies=[Depends(get_current_user)])


@router.get("", response_model=list[NewsletterResponse])
def list_newsletters(db: Session = Depends(get_db)) -> list[NewsletterResponse]:
    service = NewsletterService(db)
    return service.list_newsletters()


@router.post("/generate", response_model=NewsletterResponse, status_code=status.HTTP_201_CREATED)
def generate_newsletter(
    db: Session = Depends(get_db),
) -> NewsletterResponse:
    service = NewsletterService(db)
    return service.generate_daily_newsletter()


@router.get("/{newsletter_id}", response_model=NewsletterResponse)
def get_newsletter(
    newsletter_id: int,
    db: Session = Depends(get_db),
) -> NewsletterResponse:
    service = NewsletterService(db)
    newsletter = service.get_by_id(newsletter_id)
    if newsletter is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Newsletter not found",
        )
    return newsletter


@router.get("/{newsletter_id}/pdf")
def download_newsletter_pdf(
    newsletter_id: int,
    db: Session = Depends(get_db),
):
    service = NewsletterService(db)
    try:
        pdf_bytes = service.generate_pdf(newsletter_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    return StreamingResponse(
        iter([pdf_bytes]),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="newsletter-{newsletter_id}.pdf"'},
    )
