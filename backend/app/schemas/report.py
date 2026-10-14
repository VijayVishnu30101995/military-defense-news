from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, model_validator

# Every photo is downloaded while the PDF is built, so a report is capped.
MAX_REPORT_ARTICLES = 50


class ReportRequest(BaseModel):
    title: str = Field(default="Daily Defence News Report", min_length=1, max_length=150)
    date_from: date | None = None
    date_to: date | None = None
    # In the reader's chosen order; used as-is when `order` is "custom".
    article_ids: list[int] = Field(min_length=1, max_length=MAX_REPORT_ARTICLES)
    order: Literal["newest", "oldest", "custom"] = "newest"
    include_summary: bool = True
    include_dates: bool = True
    include_sources: bool = True
    include_images: bool = True
    include_links: bool = True

    @model_validator(mode="after")
    def _dates_in_order(self) -> "ReportRequest":
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValueError("The start date must be on or before the end date.")
        if not self.title.strip():
            raise ValueError("The report needs a title.")
        return self
