"""Cursor pages, RFC 0004 section 3. The cursor is opaque to the client."""

import base64
import binascii

from pydantic import BaseModel, Field

from ogrl.errors import FieldError, Invalid


class PageRequest(BaseModel):
    limit: int = Field(default=50, ge=1, le=200)
    cursor: str | None = None


class PageInfo(BaseModel):
    next_cursor: str | None = None  # omitted on the last page
    limit: int


class Page[T](BaseModel):
    data: list[T]
    page: PageInfo


def encode_cursor(last_id: str) -> str:
    return base64.urlsafe_b64encode(last_id.encode()).decode().rstrip("=")


def decode_cursor(cursor: str | None) -> str | None:
    if not cursor:
        return None
    try:
        return base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)).decode()
    except (binascii.Error, UnicodeDecodeError, ValueError) as exc:
        raise Invalid(
            errors=[FieldError("the cursor is not one this server issued", "/cursor")]
        ) from exc
