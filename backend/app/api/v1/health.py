from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.dependencies import require_admin
from app.database import get_db
from app.models.job_run import JobRun
from app.models.source import Source
from app.models.source_collection_job import SourceCollectionJob

router = APIRouter(
    prefix="/sources",
    tags=["Source Health"],
    dependencies=[Depends(require_admin)],
)


@router.get("/health/all")
def get_all_source_health(db: Session = Depends(get_db)) -> list[dict]:
    sources = db.query(Source).order_by(Source.name.asc()).all()
    result: list[dict] = []
    for source in sources:
        job = db.query(SourceCollectionJob).filter(SourceCollectionJob.source_id == source.id).first()
        last_run = db.query(JobRun).filter(JobRun.source_collection_job_id == job.id).order_by(JobRun.created_at.desc()).first() if job else None
        result.append(
            {
                "source_id": source.id,
                "name": source.name,
                "is_active": source.is_active,
                "status": "ok" if source.last_success_at and (datetime.utcnow() - source.last_success_at.replace(tzinfo=None)).days < 7 else "warning",
                "last_success_at": source.last_success_at.isoformat() if source.last_success_at else None,
                "last_failure_at": source.last_failure_at.isoformat() if source.last_failure_at else None,
                "job_last_run_at": last_run.started_at.isoformat() if last_run else None,
                "job_last_success_at": last_run.completed_at.isoformat() if last_run and last_run.status == "SUCCESS" and last_run.completed_at else None,
                "job_last_failure_at": last_run.completed_at.isoformat() if last_run and last_run.status == "FAILED" and last_run.completed_at else None,
                "job_last_error": last_run.error_message if last_run else None,
            }
        )
    return result


@router.post("/health/trigger")
def trigger_source_health_check(db: Session = Depends(get_db)) -> dict:
    sources = db.query(Source).count()
    return {
        "total_sources": sources,
        "critical_count": 0,
        "threshold": 3,
        "sent": False,
    }


@router.get("/{source_id}/health")
def get_source_health(source_id: int, db: Session = Depends(get_db)) -> dict:
    source = db.query(Source).filter(Source.id == source_id).first()
    if source is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source not found")

    job = db.query(SourceCollectionJob).filter(SourceCollectionJob.source_id == source.id).first()
    last_run = None
    if job:
        last_run = (
            db.query(JobRun)
            .filter(JobRun.source_collection_job_id == job.id)
            .order_by(JobRun.created_at.desc())
            .first()
        )

    return {
        "source_id": source.id,
        "name": source.name,
        "is_active": source.is_active,
        "status": "ok" if source.last_success_at and (datetime.utcnow() - source.last_success_at.replace(tzinfo=None)).days < 7 else "warning",
        "last_success_at": source.last_success_at.isoformat() if source.last_success_at else None,
        "last_failure_at": source.last_failure_at.isoformat() if source.last_failure_at else None,
        "job_last_run_at": last_run.started_at.isoformat() if last_run else None,
        "job_last_success_at": last_run.completed_at.isoformat() if last_run and last_run.status == "SUCCESS" and last_run.completed_at else None,
        "job_last_failure_at": last_run.completed_at.isoformat() if last_run and last_run.status == "FAILED" and last_run.completed_at else None,
        "job_last_error": last_run.error_message if last_run else None,
    }
