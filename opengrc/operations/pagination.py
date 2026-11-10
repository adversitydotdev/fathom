from pydantic import BaseModel, Field


class PageRequest(BaseModel):
    limit: int = Field(default=50, ge=1, le=200)
    cursor: str | None = None


class PageInfo(BaseModel):
    next_cursor: str | None = None  # omitted on the last page
    limit: int


class Page[T](BaseModel):
    data: list[T]
    page: PageInfo
