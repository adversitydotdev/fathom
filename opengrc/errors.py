"""Domain errors shared by every layer.

Operations raise these. They know nothing about HTTP. `opengrc.api.problems`
is the one place that turns them into status codes and problem+json bodies,
so an agent or the CLI calling the same operation gets the same error type.
"""

from dataclasses import dataclass, field


@dataclass
class FieldError:
    detail: str
    pointer: str | None = None  # JSON pointer into the request body


@dataclass
class OpenGRCError(Exception):
    detail: str = ""
    # The last segment of the problem URN: urn:opengrc:problem:<slug>
    slug: str = "error"

    def __post_init__(self) -> None:
        super().__init__(self.detail)


@dataclass
class Invalid(OpenGRCError):
    slug: str = "bad-request"
    errors: list[FieldError] = field(default_factory=list)


@dataclass
class Unauthenticated(OpenGRCError):
    slug: str = "unauthenticated"


@dataclass
class Forbidden(OpenGRCError):
    slug: str = "forbidden"


@dataclass
class FeatureDisabled(OpenGRCError):
    slug: str = "feature-disabled"


@dataclass
class NotFound(OpenGRCError):
    slug: str = "not-found"


@dataclass
class Conflict(OpenGRCError):
    """Library or provider row, or an id already in use. `slug` says which."""

    slug: str = "conflict"


@dataclass
class PreconditionFailed(OpenGRCError):
    slug: str = "stale-write"
