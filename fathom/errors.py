"""Domain errors shared by every layer.

Operations raise these. They know nothing about HTTP. `fathom.api.problems`
is the one place that turns them into status codes and problem+json bodies,
so an agent or the CLI calling the same operation gets the same error type.
"""

from dataclasses import dataclass, field


@dataclass
class FieldError:
    detail: str
    pointer: str | None = None  # JSON pointer into the request body


@dataclass
class FathomError(Exception):
    detail: str = ""
    # The last segment of the problem URN: urn:fathom:problem:<slug>
    slug: str = "error"

    def __post_init__(self) -> None:
        super().__init__(self.detail)


@dataclass
class Invalid(FathomError):
    slug: str = "bad-request"
    errors: list[FieldError] = field(default_factory=list)


@dataclass
class Unauthenticated(FathomError):
    slug: str = "unauthenticated"


@dataclass
class Forbidden(FathomError):
    slug: str = "forbidden"


@dataclass
class FeatureDisabled(FathomError):
    slug: str = "feature-disabled"


@dataclass
class NotFound(FathomError):
    slug: str = "not-found"


@dataclass
class Conflict(FathomError):
    """Library or provider row, or an id already in use. `slug` says which."""

    slug: str = "conflict"


@dataclass
class PreconditionFailed(FathomError):
    slug: str = "stale-write"


@dataclass
class UnsupportedMediaType(FathomError):
    slug: str = "unsupported-media-type"
