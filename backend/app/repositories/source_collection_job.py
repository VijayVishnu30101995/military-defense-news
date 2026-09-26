from sqlalchemy.orm import Session

from app.models.source_collection_job import SourceCollectionJob


class SourceCollectionJobRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_source_id(self, source_id: int) -> SourceCollectionJob | None:
        return (
            self.db.query(SourceCollectionJob)
            .filter(SourceCollectionJob.source_id == source_id)
            .first()
        )

    def create(self, source_id: int, *, is_enabled: bool, interval_minutes: int, next_run_at: object | None) -> SourceCollectionJob:
        job = SourceCollectionJob(
            source_id=source_id,
            is_enabled=is_enabled,
            interval_minutes=interval_minutes,
            next_run_at=next_run_at,
        )
        self.db.add(job)
        self.db.commit()
        self.db.refresh(job)
        return job

    def update(self, job: SourceCollectionJob, **updates) -> SourceCollectionJob:
        for field, value in updates.items():
            if value is not None:
                setattr(job, field, value)
        self.db.commit()
        self.db.refresh(job)
        return job

    def delete(self, job: SourceCollectionJob) -> None:
        self.db.delete(job)
        self.db.commit()
