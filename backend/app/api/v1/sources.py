from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.database import get_db
from app.models.source import Source
from app.models.source_collection_job import SourceCollectionJob
from app.schemas.source import SourceCreate, SourceResponse, SourceUpdate
from app.services.source import SourceService


router = APIRouter(
    prefix="/sources",
    tags=["Sources"],
    dependencies=[Depends(get_current_user)],
)


@router.get("", response_model=list[SourceResponse])
def list_sources(
    db: Session = Depends(get_db),
) -> list[SourceResponse]:
    service = SourceService(db)
    return service.get_all()

@router.patch(
    "/{source_id}",
    response_model=SourceResponse,
)
def update_source(
    source_id: int,
    source_data: SourceUpdate,
    db: Session = Depends(get_db),
) -> SourceResponse:
    service = SourceService(db)

    try:
        source = service.update(source_id, source_data)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        )

    if source is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Source not found",
        )

    return source

@router.post(
    "",
    response_model=SourceResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_source(
    source_data: SourceCreate,
    db: Session = Depends(get_db),
) -> SourceResponse:
    service = SourceService(db)

    try:
        return service.create(source_data)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        )


@router.get("/{source_id}", response_model=SourceResponse)
def get_source(
    source_id: int,
    db: Session = Depends(get_db),
) -> SourceResponse:
    service = SourceService(db)

    source = service.get_by_id(source_id)

    if source is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Source not found",
        )

    return source

@router.post(
    "/{source_id}/collect",
    status_code=status.HTTP_200_OK,
)
def collect_source(
    source_id: int,
    db: Session = Depends(get_db),
) -> dict:
    source = db.query(Source).filter(Source.id == source_id).first()
    if source is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Source not found",
        )

    job = db.query(SourceCollectionJob).filter(SourceCollectionJob.source_id == source_id).first()
    if job is None:
        job = SourceCollectionJob(
            source_id=source_id,
            is_enabled=True,
            interval_minutes=source.collection_frequency,
            next_run_at=datetime.utcnow() + timedelta(minutes=5),
        )
        db.add(job)
        db.commit()
        db.refresh(job)

    source.last_success_at = datetime.utcnow()
    db.commit()

    return {
        "source_id": source.id,
        "name": source.name,
        "status": "ok",
        "last_success_at": source.last_success_at.isoformat(),
    }


@router.delete(
    "/{source_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_source(
    source_id: int,
    db: Session = Depends(get_db),
) -> None:
    service = SourceService(db)

    deleted = service.delete(source_id)

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Source not found",
        )
