"""RFC 0001 objects as Pydantic models.

The response body is the object (RFC 0004 section 3), so these models are
also the API's response schemas. Only `Control` is sketched; the rest of the
object model follows the same shape.
"""

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

SPEC_VERSION = "0.1.0"


class ExternalReference(BaseModel):
    source_name: str
    url: str | None = None
    external_id: str | None = None


class Envelope(BaseModel):
    """Fields every object carries."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    type: str
    id: str
    spec_version: Literal["0.1.0"] = SPEC_VERSION
    created: datetime
    modified: datetime
    name: str | None = None
    revoked: bool = False
    created_by_ref: str | None = None
    tags: list[str] = Field(default_factory=list)
    external_references: list[ExternalReference] = Field(default_factory=list)
    extensions: dict[str, Any] = Field(default_factory=dict)
    lang: str | None = None


class Origin(StrEnum):
    STANDARD = "standard"
    CUSTOM = "custom"


class ControlType(StrEnum):
    PREVENTIVE = "preventive"
    DETECTIVE = "detective"
    CORRECTIVE = "corrective"


class Frequency(StrEnum):
    CONTINUOUS = "continuous"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    ANNUAL = "annual"
    EVENT_DRIVEN = "event-driven"


class Parameter(BaseModel):
    label: str | None = None
    value: str | None = None


class Control(Envelope):
    type: Literal["control"] = "control"
    name: str
    origin: Origin
    display_id: str | None = None
    family: str | None = None
    control_type: ControlType | None = None
    frequency: Frequency | None = None
    summary: str | None = None
    statement: str
    objective: str
    guidance: str | None = None
    parameters: dict[str, Parameter] = Field(default_factory=dict)

    @property
    def read_only(self) -> bool:
        """Library rows are not editable here (RFC 0004 section 3)."""
        return self.origin is Origin.STANDARD
