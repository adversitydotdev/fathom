"""Domain errors shared by every layer.

Operations raise these. They know nothing about HTTP. `ogrl.api.problems`
is the one place that turns them into status codes and problem+json bodies,
so an agent or the CLI calling the same operation gets the same error type.
"""

from dataclasses import dataclass, field


@dataclass
class FieldError:
    detail: str
    pointer: str | None = None  # JSON pointer into the request body


@dataclass
class OGRLError(Exception):
    detail: str = ""
    # The last segment of the problem URN: urn:ogrl:problem:<slug>
    slug: str = "error"

    def __post_init__(self) -> None:
        super().__init__(self.detail)


@dataclass
class Invalid(OGRLError):
    slug: str = "bad-request"
    errors: list[FieldError] = field(default_factory=list)


@dataclass
class Unauthenticated(OGRLError):
    slug: str = "unauthenticated"


@dataclass
class Forbidden(OGRLError):
    slug: str = "forbidden"


@dataclass
class FeatureDisabled(OGRLError):
    slug: str = "feature-disabled"


@dataclass
class NotFound(OGRLError):
    slug: str = "not-found"


@dataclass
class Conflict(OGRLError):
    """Library or provider row, or an id already in use. `slug` says which."""

    slug: str = "conflict"


@dataclass
class PreconditionFailed(OGRLError):
    slug: str = "stale-write"


@dataclass
class UnsupportedMediaType(OGRLError):
    slug: str = "unsupported-media-type"
