from sqlalchemy.orm import Session

from app.models.source import Source
from app.schemas.source import SourceCreate, SourceUpdate


class SourceRepository:
    """Database operations for Source."""

    def __init__(self, db: Session):
        self.db = db

    def get_all(self) -> list[Source]:
        return (
            self.db.query(Source)
            .order_by(Source.name.asc())
            .all()
        )

    def get_by_id(self, source_id: int) -> Source | None:
        return (
            self.db.query(Source)
            .filter(Source.id == source_id)
            .first()
        )

    def get_by_name(self, name: str) -> Source | None:
        return (
            self.db.query(Source)
            .filter(Source.name == name)
            .first()
        )

    def create(self, source_data: SourceCreate) -> Source:
        data = source_data.model_dump()

        data["website_url"] = str(data["website_url"])

        if data["feed_url"] is not None:
            data["feed_url"] = str(data["feed_url"])

        source = Source(**data)

        self.db.add(source)
        self.db.commit()
        self.db.refresh(source)

        return source

    def update(
        self,
        source: Source,
        source_data: SourceUpdate,
    ) -> Source:
        updates = source_data.model_dump(exclude_unset=True)

        if "website_url" in updates:
            updates["website_url"] = str(updates["website_url"])

        if "feed_url" in updates and updates["feed_url"] is not None:
            updates["feed_url"] = str(updates["feed_url"])

        for field, value in updates.items():
            setattr(source, field, value)

        self.db.commit()
        self.db.refresh(source)

        return source

    def delete(self, source: Source) -> None:
        self.db.delete(source)
        self.db.commit()
