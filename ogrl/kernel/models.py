"""RFC 0001 objects as Pydantic models.

The response body is the object (RFC 0004 section 3), so these models are
also the API's response schemas. Every model keeps fields it does not know
(`extra="allow"`): a field the server does not understand is stored and
returned, which is the round-trip rule in RFC 0001 section 5.

Fields with no value are `None` and are dropped on output. Null is invalid
in the language, so an absent field and a `None` field mean the same thing.
"""

from datetime import date, datetime
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, field_validator

from ogrl.kernel.timeutil import utc

SPEC_VERSION = "0.1.0"
# Readable library revisions (RFC 0001 §6.2). Organization objects still stamp 0.1.0 for now.
READABLE_SPEC_MAJOR_MINORS = frozenset({"0.1", "0.2"})

Timestamp = Annotated[datetime, AfterValidator(utc)]
Score = Annotated[int, Field(ge=1, le=5)]


def readable_spec_version(value: str) -> bool:
    """A reader accepts the major and minor it implements, at any patch (6.2)."""
    parts = value.split(".")
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        return False
    return f"{parts[0]}.{parts[1]}" in READABLE_SPEC_MAJOR_MINORS


class Part(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)


class ExternalReference(Part):
    source: str | None = None
    url: str | None = None
    description: str | None = None


class Digest(Part):
    algorithm: Literal["sha-256"]
    value: str


class Resource(Part):
    uri: str | None = None
    media_type: str | None = None
    digest: Digest | None = None


class Envelope(BaseModel):
    """Fields every object carries (RFC 0001 section 6.2)."""

    model_config = ConfigDict(extra="allow", frozen=True, populate_by_name=True)

    type: str
    id: str
    spec_version: str = SPEC_VERSION
    created: Timestamp
    modified: Timestamp
    name: str | None = None
    revoked: bool | None = None
    created_by_ref: str | None = None
    tags: list[str] | None = None
    external_references: list[ExternalReference] | None = None
    extensions: dict[str, Any] | None = None
    lang: str | None = None

    @field_validator("spec_version")
    @classmethod
    def _readable(cls, value: str) -> str:
        if not readable_spec_version(value):
            supported = ", ".join(sorted(f"{minor}.x" for minor in READABLE_SPEC_MAJOR_MINORS))
            raise ValueError(f"spec_version {value} is not readable; supported {supported}")
        return value

    @property
    def is_revoked(self) -> bool:
        return bool(self.revoked)

    def body(self) -> dict[str, Any]:
        """The JSON form: aliases, no `None`, dates as strings."""
        return self.model_dump(mode="json", by_alias=True, exclude_none=True)


# --- Library -----------------------------------------------------------------


class Framework(Envelope):
    type: Literal["framework"] = "framework"
    name: str
    publisher: str
    version: str
    reproduction: Literal["permitted", "citation-only"]
    source: dict[str, Any] | None = None


class RequirementClass(StrEnum):
    CRITERION = "criterion"
    CONTROL = "control"
    ENHANCEMENT = "enhancement"
    CLAUSE = "clause"
    SPECIFICATION = "specification"


class Parameter(Part):
    label: str | None = None
    value: str | None = None


class RequirementPart(Part):
    id: str
    name: str | None = None
    statement: str


class Method(Part):
    method: Literal["examine", "interview", "test"]
    statement: str | None = None


class Objective(Part):
    id: str
    statement: str
    methods: list[Method] | None = None


class Requirement(Envelope):
    type: Literal["requirement"] = "requirement"
    name: str
    framework_ref: str
    class_: RequirementClass = Field(alias="class")
    display_id: str | None = None
    withdrawn: bool | None = None
    statement: str | None = None
    citation: str | None = None
    parameters: dict[str, Parameter] | None = None
    parts: list[RequirementPart] | None = None
    objectives: list[Objective] | None = None

    @property
    def is_withdrawn(self) -> bool:
        return bool(self.withdrawn)


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
    parameters: dict[str, Parameter] | None = None


Relationship = Literal[
    "equal-to", "equivalent-to", "subset-of", "superset-of", "intersects-with", "no-relationship"
]
FULL_COVERAGE = frozenset({"equal-to", "equivalent-to", "superset-of"})
CONTRIBUTION = frozenset({"subset-of", "intersects-with"})


class Mapping(Envelope):
    type: Literal["mapping"] = "mapping"
    source_ref: str
    target_ref: str
    relationship: Relationship
    rationale: Literal["functional", "semantic", "syntactic"] | None = None
    review_status: Literal["draft", "reviewed"] | None = None
    confidence: Literal["low", "medium", "high"] | None = None
    summary: str | None = None
    parameter_map: dict[str, str] | None = None
    combined_with_refs: list[str] | None = None


class Baseline(Envelope):
    type: Literal["baseline"] = "baseline"
    name: str
    extends_ref: str | None = None
    framework_refs: list[str] | None = None
    control_refs: list[str] | None = None
    requirement_refs: list[str] | None = None
    parameter_bindings: dict[str, dict[str, str]] | None = None


Interval = Literal[
    "continuous", "daily", "weekly", "monthly", "quarterly", "annual", "event-driven"
]


class RunEvidence(Part):
    path: str
    name: str
    media_type: str


class Run(Part):
    """A test's `run` block. Which fields apply depends on `runner` (RFC 0001 section 7.6)."""

    runner: str
    # shell
    command: str | None = None
    timeout: str | None = None
    env: list[str] | None = None
    evidence: list[RunEvidence] | None = None
    # rule
    source: str | None = None
    select: str | None = None
    assert_: str | None = Field(default=None, alias="assert")
    aggregate: str | None = None
    subject: str | None = None
    allow_empty: bool | None = None
    # integration
    check: str | None = None
    sources: list[str] | None = None
    with_: dict[str, str] | None = Field(default=None, alias="with")

    def sources_read(self) -> list[str]:
        """Every source the run evaluates, in the order the test lists them."""
        if self.runner == "rule":
            return [self.source] if self.source else []
        if self.runner == "integration":
            return list(self.sources or [])
        return []


class Test(Envelope):
    __test__ = False  # not a pytest class

    type: Literal["test"] = "test"
    name: str
    control_ref: str
    method: Literal["automated", "manual"]
    fulfills_ref: str | None = None
    system_refs: list[str] | None = None
    objective_refs: list[str] | None = None
    interval: Interval | None = None
    required: bool | None = None
    description: str | None = None
    procedure_ref: str | None = None
    run: Run | None = None


# --- Organization --------------------------------------------------------------


class Party(Envelope):
    type: Literal["party"] = "party"
    name: str
    kind: Literal["person", "team", "role", "organization"]


class Component(Envelope):
    type: Literal["component"] = "component"
    name: str
    kind: Literal["infrastructure", "software", "people", "data", "procedure", "service"]
    description: str | None = None
    party_ref: str | None = None


Impact = Literal["low", "moderate", "high"]


class InformationType(Part):
    name: str
    description: str | None = None
    confidentiality: Impact
    integrity: Impact
    availability: Impact
    component_refs: list[str] | None = None


class Authorization(Part):
    identifier: str
    authorized: date
    expires: date


class SystemParty(Part):
    party_ref: str
    role: Literal["subservice", "customer", "operator"]
    function: str | None = None
    authorization: Authorization | None = None


class System(Envelope):
    type: Literal["system"] = "system"
    name: str
    function: str | None = None
    boundary: str | None = None
    component_refs: list[str] | None = None
    information_types: list[InformationType] | None = None
    parties: list[SystemParty] | None = None


class Program(Envelope):
    type: Literal["program"] = "program"
    name: str
    system_ref: str
    baseline_ref: str


ImplementationStatus = Literal["planned", "implemented", "partial", "not-applicable", "exception"]
Responsibility = Literal["provider", "customer", "shared", "subservice"]


class Implementation(Envelope):
    type: Literal["implementation"] = "implementation"
    system_ref: str | None = None
    component_ref: str | None = None
    control_ref: str | None = None
    requirement_ref: str | None = None
    status: ImplementationStatus
    responsibility: Responsibility
    subservice_ref: str | None = None
    origin: Literal["organization", "provider"] | None = None
    parameter_values: dict[str, str] | None = None
    requirement_parameter_values: dict[str, dict[str, str]] | None = None
    owner_ref: str | None = None
    narrative: str | None = None
    customer_responsibility: str | None = None

    @property
    def is_provider(self) -> bool:
        return self.origin == "provider"


class Subject(Part):
    kind: str
    name: str
    external_id: str | None = None


class Result(Envelope):
    type: Literal["result"] = "result"
    test_ref: str
    implementation_ref: str
    observed: Timestamp
    outcome: Literal["pass", "fail", "error", "skip"]
    summary: str | None = None
    valid_until: Timestamp | None = None
    objective_refs: list[str] | None = None
    evidence_refs: list[str] | None = None
    subjects: list[Subject] | None = None


class Finding(Envelope):
    type: Literal["finding"] = "finding"
    name: str
    system_ref: str
    objective_ref: str
    determination: Literal["satisfied", "not-satisfied"]
    observed: date
    narrative: str
    implementation_ref: str | None = None
    evidence_refs: list[str] | None = None
    risk_ref: str | None = None


EvidenceMethod = Literal["automated", "upload", "attestation", "link"]
DIGEST_REQUIRED = frozenset({"automated", "upload", "attestation"})
# Fields RFC 0001 section 7.14 freezes once evidence is complete.
EVIDENCE_FROZEN = (
    "resource",
    "method",
    "collected",
    "valid_from",
    "valid_until",
    "implementation_ref",
    "result_ref",
)


class Evidence(Envelope):
    type: Literal["evidence"] = "evidence"
    name: str
    method: EvidenceMethod
    collected: Timestamp | None = None
    valid_from: date | None = None
    valid_until: date | None = None
    implementation_ref: str | None = None
    result_ref: str | None = None
    resource: Resource | None = None

    @property
    def complete(self) -> bool:
        """RFC 0001 section 7.14. Incomplete evidence never counts toward status."""
        if self.method in DIGEST_REQUIRED:
            return self.resource is not None and self.resource.digest is not None
        return True


DocumentStatus = Literal["draft", "adopted", "retired"]


class Policy(Envelope):
    type: Literal["policy"] = "policy"
    name: str
    status: DocumentStatus
    version: str | None = None
    adopted: date | None = None
    reviewed: date | None = None
    review_interval: str | None = None
    owner_ref: str | None = None
    control_refs: list[str] | None = None
    resource: Resource | None = None


class Procedure(Envelope):
    type: Literal["procedure"] = "procedure"
    name: str
    status: DocumentStatus
    policy_ref: str | None = None
    control_refs: list[str] | None = None
    interval: str | None = None
    owner_ref: str | None = None
    resource: Resource | None = None


class Milestone(Part):
    name: str
    due: date
    done: date | None = None


class Risk(Envelope):
    type: Literal["risk"] = "risk"
    name: str
    statement: str
    likelihood: Score
    impact: Score
    residual_likelihood: Score | None = None
    residual_impact: Score | None = None
    treatment: Literal["mitigate", "accept", "transfer", "avoid"]
    status: Literal["open", "treating", "accepted", "closed"]
    system_ref: str | None = None
    owner_ref: str | None = None
    approver_ref: str | None = None
    control_refs: list[str] | None = None
    review_on: date | None = None
    milestones: list[Milestone] | None = None


class Exception_(Envelope):
    """`exception` in the language. The trailing underscore avoids the builtin."""

    type: Literal["exception"] = "exception"
    implementation_ref: str
    justification: str
    expires: date
    approver_ref: str
    risk_ref: str | None = None


class MappingReview(Envelope):
    type: Literal["mapping_review"] = "mapping_review"
    mapping_ref: str
    library_version: str
    mapping_modified: Timestamp | None = None
    review_status: Literal["reviewed", "rejected"]
    summary: str | None = None


MODELS: dict[str, type[Envelope]] = {
    model.model_fields["type"].default: model
    for model in (
        Framework,
        Requirement,
        Control,
        Mapping,
        Baseline,
        Test,
        Party,
        Component,
        System,
        Program,
        Implementation,
        Result,
        Finding,
        Evidence,
        Policy,
        Procedure,
        Risk,
        Exception_,
        MappingReview,
    )
}

LIBRARY_TYPES = frozenset({"framework", "requirement", "control", "mapping", "baseline", "test"})
PROVIDER_TYPES = frozenset({"party", "component", "implementation", "evidence", "test"})


def parse(body: dict[str, Any]) -> Envelope:
    """Validate one object of any type. Raises ValueError or pydantic.ValidationError."""
    kind = body.get("type")
    model = MODELS.get(kind) if isinstance(kind, str) else None
    if model is None:
        raise ValueError(f"unknown type {kind!r}")
    return model.model_validate(body)
