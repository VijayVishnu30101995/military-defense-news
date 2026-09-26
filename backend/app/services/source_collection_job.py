from datetime import datetime

from sqlalchemy.orm import Session

from app.models.source_collection_job import SourceCollectionJob
from app.repositories.source_collection_job import SourceCollectionJobRepository
from app.schemas.source_collection_job import SourceCollectionJobCreate, SourceCollectionJobUpdate


class SourceCollectionJobService:
    def __init__(self, db: Session):
        self.repository = SourceCollectionJobRepository(db)

    def get_by_source_id(self, source_id: int) -> SourceCollectionJob | None:
        return self.repository.get_by_source_id(source_id)

    def create(self, source_id: int, data: SourceCollectionJobCreate) -> SourceCollectionJob:
        existing = self.repository.get_by_source_id(source_id)
        if existing is not None:
            return self.repository.update(
                existing,
                is_enabled=data.is_enabled,
                interval_minutes=data.interval_minutes,
                next_run_at=data.next_run_at,
            )
        return self.repository.create(
            source_id,
            is_enabled=data.is_enabled,
            interval_minutes=data.interval_minutes,
            next_run_at=data.next_run_at,
        )

    def update(self, source_id: int, data: SourceCollectionJobUpdate) -> SourceCollectionJob | None:
        job = self.repository.get_by_source_id(source_id)
        if job is None:
            return None
        updates = data.model_dump(exclude_unset=True)
        return self.repository.update(job, **updates)

    def delete(self, source_id: int) -> bool:
        job = self.repository.get_by_source_id(source_id)
        if job is None:
            return False
        self.repository.delete(job)
        return True
