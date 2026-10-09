from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, require_admin
from app.database import get_db
from app.models.source import Source
from app.models.source_collection_job import SourceCollectionJob
from app.schemas.source import SourceCreate, SourceResponse, SourceUpdate
from app.schemas.source_collection_job import (
    SourceCollectionJobCreate,
    SourceCollectionJobResponse,
    SourceCollectionJobUpdate,
)
from app.schemas.collection import CollectionRunRequest, CollectionRunResponse
from app.services.article import ArticleService
from app.services.collection_run import (
    CollectionAlreadyRunning,
    collection_lock,
    latest_run_snapshot,
    start_collection_run,
)
from app.services.collector import SourceCollectorService
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


@router.post(
    "/collection-runs",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_admin)],
)
def start_collection_run_endpoint(payload: CollectionRunRequest | None = None) -> dict:
    try:
        return start_collection_run(payload.source_ids if payload else None)
    except CollectionAlreadyRunning as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.get(
    "/collection-runs/latest",
    dependencies=[Depends(require_admin)],
)
def latest_collection_run_endpoint() -> dict:
    return latest_run_snapshot()


@router.get(
    "/{source_id}/job",
    response_model=SourceCollectionJobResponse,
    dependencies=[Depends(require_admin)],
)
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
    dependencies=[Depends(require_admin)],
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
    dependencies=[Depends(require_admin)],
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
    dependencies=[Depends(require_admin)],
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
    dependencies=[Depends(require_admin)],
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
    dependencies=[Depends(require_admin)],
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
    response_model=CollectionRunResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_admin)],
)
def collect_source_endpoint(
    source_id: int,
    db: Session = Depends(get_db),
) -> CollectionRunResponse:
    source = db.query(Source).filter(Source.id == source_id).first()
    if source is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Source not found",
        )

    if not collection_lock.acquire(blocking=False):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A collection is already in progress. Try again when it finishes.",
        )
    try:
        return SourceCollectorService(db).collect_source(source_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
    finally:
        collection_lock.release()


@router.delete(
    "/{source_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_admin)],
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
