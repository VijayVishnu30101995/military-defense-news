from typing import Literal

from pydantic import BaseModel, Field, field_validator

MAX_WATCHLISTS_PER_USER = 20
MAX_TERMS = 20


def _clean_terms(values: list[str]) -> list[str]:
    """Trim and de-duplicate (ignoring case), keeping the reader's spelling and order."""
    kept: dict[str, str] = {}
    for value in values:
        term = " ".join(value.split())
        if not term:
            continue
        if len(term) < 2 or len(term) > 80:
            raise ValueError("Each term must be 2 to 80 characters long.")
        kept.setdefault(term.lower(), term)
    if len(kept) > MAX_TERMS:
        raise ValueError(f"Use at most {MAX_TERMS} terms.")
    return list(kept.values())


class WatchlistTerms(BaseModel):
    terms: list[str] = Field(max_length=100)
    exclude_terms: list[str] = Field(default_factory=list, max_length=100)

    @field_validator("terms", "exclude_terms")
    @classmethod
    def _clean(cls, values: list[str]) -> list[str]:
        return _clean_terms(values)

    @field_validator("terms")
    @classmethod
    def _need_one(cls, values: list[str]) -> list[str]:
        if not values:
            raise ValueError("Add at least one word or phrase to watch for.")
        return values


class WatchlistCreate(WatchlistTerms):
    name: str = Field(min_length=1, max_length=100)
    email_frequency: Literal["off", "instant", "daily"] = "off"

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        value = " ".join(value.split())
        if not value:
            raise ValueError("The watchlist needs a name.")
        return value


class WatchlistUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    terms: list[str] | None = Field(default=None, max_length=100)
    exclude_terms: list[str] | None = Field(default=None, max_length=100)
    email_frequency: Literal["off", "instant", "daily"] | None = None
    is_active: bool | None = None

    _name = field_validator("name")(WatchlistCreate._name.__func__)

    @field_validator("terms", "exclude_terms")
    @classmethod
    def _clean(cls, values: list[str] | None) -> list[str] | None:
        return None if values is None else _clean_terms(values)

    @field_validator("terms")
    @classmethod
    def _need_one(cls, values: list[str] | None) -> list[str] | None:
        if values is not None and not values:
            raise ValueError("Add at least one word or phrase to watch for.")
        return values
