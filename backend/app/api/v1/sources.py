from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.database import get_db
from app.schemas.article import ArticleCreate, ArticleResponse
from app.schemas.collection import CollectionRunResponse
from app.schemas.source import SourceCreate, SourceResponse, SourceUpdate
from app.schemas.source_collection_job import (
    SourceCollectionJobCreate,
    SourceCollectionJobResponse,
    SourceCollectionJobUpdate,
)
from app.services.article import ArticleService
from app.services.collector import SourceCollectorService
from app.services.scheduler import run_due_collection_jobs
from app.services.source import SourceService
from app.services.source_collection_job import SourceCollectionJobService


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


@router.get("/{source_id}/job", response_model=SourceCollectionJobResponse)
def get_source_collection_job(
    source_id: int,
    db: Session = Depends(get_db),
) -> SourceCollectionJobResponse:
    source_service = SourceService(db)
    if source_service.get_by_id(source_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Source not found",
        )

    service = SourceCollectionJobService(db)
    job = service.get_by_source_id(source_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Source collection job not found",
        )
    return job


@router.post(
    "/{source_id}/job",
    response_model=SourceCollectionJobResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_source_collection_job(
    source_id: int,
    job_data: SourceCollectionJobCreate,
    db: Session = Depends(get_db),
) -> SourceCollectionJobResponse:
    source_service = SourceService(db)
    if source_service.get_by_id(source_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Source not found",
        )

    service = SourceCollectionJobService(db)
    return service.create(source_id, job_data)


@router.patch(
    "/{source_id}/job",
    response_model=SourceCollectionJobResponse,
)
def update_source_collection_job(
    source_id: int,
    job_data: SourceCollectionJobUpdate,
    db: Session = Depends(get_db),
) -> SourceCollectionJobResponse:
    source_service = SourceService(db)
    if source_service.get_by_id(source_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Source not found",
        )

    service = SourceCollectionJobService(db)
    job = service.update(source_id, job_data)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Source collection job not found",
        )
    return job


@router.delete(
    "/{source_id}/job",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_source_collection_job(
    source_id: int,
    db: Session = Depends(get_db),
) -> None:
    source_service = SourceService(db)
    if source_service.get_by_id(source_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Source not found",
        )

    service = SourceCollectionJobService(db)
    deleted = service.delete(source_id)

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Source collection job not found",
        )


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
    "/{source_id}/articles",
    response_model=ArticleResponse,
)
def create_article_for_source(
    source_id: int,
    article_data: ArticleCreate,
    db: Session = Depends(get_db),
) -> ArticleResponse:
    source_service = SourceService(db)
    if source_service.get_by_id(source_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Source not found",
        )

    payload = article_data.model_copy(update={"source_id": source_id})
    service = ArticleService(db)
    return service.create(payload)


@router.post(
    "/{source_id}/collect",
    response_model=CollectionRunResponse,
    status_code=status.HTTP_200_OK,
)
def collect_source(
    source_id: int,
    db: Session = Depends(get_db),
) -> CollectionRunResponse:
    service = SourceCollectorService(db)
    try:
        return service.collect_source(source_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc


@router.post(
    "/collect/all",
    response_model=dict[str, int],
    status_code=status.HTTP_200_OK,
)
def collect_all_sources(
    db: Session = Depends(get_db),
) -> dict[str, int]:
    _ = db
    run_due_collection_jobs()
    return {"processed": 1}


@router.get("/{source_id}/health", response_model=dict)
def get_source_health(
    source_id: int,
    db: Session = Depends(get_db),
) -> dict:
    """Return basic health information for a source and its collection job."""
    source_service = SourceService(db)
    source = source_service.get_by_id(source_id)
    if source is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Source not found",
        )

    job_service = SourceCollectionJobService(db)
    job = job_service.get_by_source_id(source_id)

    return {
        "source_id": source.id,
        "name": source.name,
        "is_active": source.is_active,
        "last_success_at": source.last_success_at,
        "last_failure_at": source.last_failure_at,
        "job_last_run_at": job.last_run_at if job else None,
        "job_last_success_at": job.last_success_at if job else None,
        "job_last_failure_at": job.last_failure_at if job else None,
        "job_last_error": job.last_error if job else None,
    }


@router.post("/health/trigger", response_model=dict)
def trigger_health_alerts(
    db: Session = Depends(get_db),
) -> dict:
    """Manually trigger the health alert check and return the result.

    This is useful for operators to immediately evaluate and send alerts.
    """
    try:
        from app.services.scheduler import run_health_alert_check
        result = run_health_alert_check()
        return result
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@router.get("/health/all", response_model=list[dict])
def list_sources_health(
    db: Session = Depends(get_db),
) -> list[dict]:
    """Return aggregated health information for all sources with a computed status.

    Status rules (based on collection_frequency in minutes):
      - paused: source is not active
      - critical: never had a successful collection or last_success_at older than 6x frequency
      - warning: last_success_at older than 2x frequency
      - ok: last_success_at within 2x frequency
    """
    from datetime import datetime, timezone

    service = SourceService(db)
    sources = service.get_all()
    now = datetime.now(timezone.utc)
    results: list[dict] = []

    for s in sources:
        if not s.is_active:
            status = "paused"
        elif s.last_success_at is None:
            status = "critical"
        else:
            delta_minutes = (now - s.last_success_at).total_seconds() / 60.0
            if delta_minutes > (s.collection_frequency * 6):
                status = "critical"
            elif delta_minutes > (s.collection_frequency * 2):
                status = "warning"
            else:
                status = "ok"

        results.append(
            {
                "source_id": s.id,
                "name": s.name,
                "is_active": s.is_active,
                "collection_frequency": s.collection_frequency,
                "reliability_score": s.reliability_score,
                "last_success_at": s.last_success_at,
                "last_failure_at": s.last_failure_at,
                "status": status,
            }
        )

    return results


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
