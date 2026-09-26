from datetime import datetime

from pydantic import BaseModel, ConfigDict


class SourceCollectionJobBase(BaseModel):
    is_enabled: bool = True
    interval_minutes: int = 360
    next_run_at: datetime | None = None


class SourceCollectionJobCreate(SourceCollectionJobBase):
    pass


class SourceCollectionJobUpdate(BaseModel):
    is_enabled: bool | None = None
    interval_minutes: int | None = None
    next_run_at: datetime | None = None


class SourceCollectionJobResponse(SourceCollectionJobBase):
    id: int
    source_id: int
    last_run_at: datetime | None = None
    last_success_at: datetime | None = None
    last_failure_at: datetime | None = None
    last_error: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
