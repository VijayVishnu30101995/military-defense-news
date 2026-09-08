from sqlalchemy.orm import Session

from app.models.source import Source
from app.repositories.source import SourceRepository
from app.schemas.source import SourceCreate, SourceUpdate


class SourceService:
    """Business logic for Source."""

    def __init__(self, db: Session):
        self.repository = SourceRepository(db)

    def get_all(self) -> list[Source]:
        return self.repository.get_all()

    def get_by_id(self, source_id: int) -> Source | None:
        return self.repository.get_by_id(source_id)

    def create(self, source_data: SourceCreate) -> Source:
        existing_source = self.repository.get_by_name(source_data.name)

        if existing_source is not None:
            raise ValueError("A source with this name already exists")

        return self.repository.create(source_data)

    def update(
        self,
        source_id: int,
        source_data: SourceUpdate,
    ) -> Source | None:
        source = self.repository.get_by_id(source_id)

        if source is None:
            return None

        if source_data.name is not None:
            existing_source = self.repository.get_by_name(source_data.name)

            if (
                existing_source is not None
                and existing_source.id != source.id
            ):
                raise ValueError("A source with this name already exists")

        return self.repository.update(source, source_data)

    def delete(self, source_id: int) -> bool:
        source = self.repository.get_by_id(source_id)

        if source is None:
            return False

        self.repository.delete(source)
        return True
