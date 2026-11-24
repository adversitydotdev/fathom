"""Records the application keeps beside the objects: pins and jobs.

These are not RFC 0001 objects. They are the store's bookkeeping, and their
shapes are `LibraryPin`, `ProviderPin`, and `Job` in api/openapi.yaml.
"""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

LIBRARY = "library"
ORGANIZATION = "organization"
PROVIDER_PREFIX = "provider:"


def provider_source(bundle_id: str) -> str:
    return PROVIDER_PREFIX + bundle_id


class LibraryPin(BaseModel):
    id: str = "bundle--ogrl-library"
    version: str
    commit: str | None = None


class ProviderPin(BaseModel):
    id: str
    name: str | None = None
    version: str
    digest: str | None = None
    kind: Literal["ogrl", "oscal-component"] | None = None
    # A hash of the stored objects, independent of how the bundle was fetched.
    # The snapshot manifest carries it so a restore can check the copy under
    # provider/ (RFC 0002 section 8.1, step 3).
    projection_digest: str | None = None


JobType = Literal[
    "library_pull",
    "provider_import",
    "test_run",
    "render",
    "git_export",
    "restore",
    "collection",
    "integration_install",
]
JobStatus = Literal["queued", "running", "succeeded", "failed"]


class JobProblem(BaseModel):
    type: str
    title: str
    status: int
    detail: str | None = None
    errors: list[dict[str, str]] | None = None


class Job(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    type: JobType
    status: JobStatus
    created: datetime
    finished: datetime | None = None
    error: JobProblem | None = None
    result_id: str | None = None
    files: list[str] | None = None
    # What the job was asked to do, and what it found. Not in the spec's
    # required set; returned so a caller can read a pull's report.
    request: dict[str, Any] = Field(default_factory=dict)
    report: dict[str, Any] | None = None
    created_by_ref: str | None = None
