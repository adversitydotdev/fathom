"""One `TypeSpec` per object type: the write and query models from
api/openapi.yaml, the permissions, the fields the server owns, and the
writes an agent may not make (RFC 0003 section 4).

Write models accept the envelope fields and keep unknown fields, because a
field the server does not know is stored and returned (RFC 0004 section 3).
Graph constraints are not here; they are the kernel's.
"""

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ogrl.access import Permission as P
from ogrl.errors import Conflict, FieldError, Invalid
from ogrl.kernel import ids
from ogrl.kernel.models import (
    EVIDENCE_FROZEN,
    Baseline,
    Component,
    Control,
    ControlType,
    DocumentStatus,
    Envelope,
    Evidence,
    EvidenceMethod,
    Exception_,
    ExternalReference,
    Finding,
    Framework,
    Frequency,
    Implementation,
    ImplementationStatus,
    InformationType,
    Interval,
    Mapping,
    MappingReview,
    Milestone,
    Origin,
    Parameter,
    Party,
    Policy,
    Procedure,
    Program,
    Relationship,
    Requirement,
    RequirementClass,
    Resource,
    Responsibility,
    Result,
    Risk,
    Run,
    Score,
    Subject,
    System,
    SystemParty,
    Test,
)
from ogrl.operations.objects import SERVER_FIELDS, TypeSpec, WriteContext
from ogrl.operations.pagination import PageRequest
from ogrl.operations.records import LIBRARY, PROVIDER_PREFIX
from ogrl.operations.store import Row

# --- write models ------------------------------------------------------------------------


class EnvelopeWrite(BaseModel):
    """`EnvelopeWrite`: the optional envelope fields every create and update accepts."""

    model_config = ConfigDict(extra="allow")

    id: str | None = None
    name: str | None = None
    tags: list[str] | None = None
    external_references: list[ExternalReference] | None = None
    extensions: dict[str, Any] | None = None
    lang: str | None = None


class ControlWrite(EnvelopeWrite):
    name: str
    statement: str
    objective: str
    display_id: str | None = None
    family: str | None = None
    control_type: ControlType | None = None
    frequency: Frequency | None = None
    summary: str | None = None
    guidance: str | None = None
    parameters: dict[str, Parameter] | None = None


class MappingWrite(EnvelopeWrite):
    source_ref: str
    target_ref: str
    relationship: Relationship
    rationale: Literal["functional", "semantic", "syntactic"] | None = None
    review_status: Literal["draft", "reviewed"] | None = None
    confidence: Literal["low", "medium", "high"] | None = None
    summary: str | None = None
    parameter_map: dict[str, str] | None = None
    combined_with_refs: list[str] | None = None


class BaselineWrite(EnvelopeWrite):
    name: str
    extends_ref: str | None = None
    framework_refs: list[str] | None = None
    control_refs: list[str] | None = None
    requirement_refs: list[str] | None = None
    parameter_bindings: dict[str, dict[str, str]] | None = None


class TestWrite(EnvelopeWrite):
    __test__ = False

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


class PartyWrite(EnvelopeWrite):
    name: str
    kind: Literal["person", "team", "role", "organization"]


class ComponentWrite(EnvelopeWrite):
    name: str
    kind: Literal["infrastructure", "software", "people", "data", "procedure", "service"]
    description: str | None = None
    party_ref: str | None = None


class SystemWrite(EnvelopeWrite):
    name: str
    function: str | None = None
    boundary: str | None = None
    component_refs: list[str] | None = None
    information_types: list[InformationType] | None = None
    parties: list[SystemParty] | None = None


class ProgramWrite(EnvelopeWrite):
    name: str
    system_ref: str
    baseline_ref: str


class ImplementationWrite(EnvelopeWrite):
    system_ref: str | None = None
    component_ref: str | None = None
    control_ref: str | None = None
    requirement_ref: str | None = None
    status: ImplementationStatus
    responsibility: Responsibility
    subservice_ref: str | None = None
    parameter_values: dict[str, str] | None = None
    requirement_parameter_values: dict[str, dict[str, str]] | None = None
    owner_ref: str | None = None
    narrative: str | None = None
    customer_responsibility: str | None = None


class ResultWrite(EnvelopeWrite):
    test_ref: str
    implementation_ref: str
    observed: datetime
    outcome: Literal["pass", "fail", "error", "skip"]
    summary: str | None = None
    valid_until: datetime | None = None
    objective_refs: list[str] | None = None
    evidence_refs: list[str] | None = None
    subjects: list[Subject] | None = None


class EvidenceWrite(EnvelopeWrite):
    name: str
    method: EvidenceMethod
    collected: datetime | None = None
    valid_from: date | None = None
    valid_until: date | None = None
    implementation_ref: str | None = None
    result_ref: str | None = None
    resource: Resource | None = None


class FindingWrite(EnvelopeWrite):
    name: str
    system_ref: str
    objective_ref: str
    determination: Literal["satisfied", "not-satisfied"]
    observed: date
    narrative: str
    implementation_ref: str | None = None
    evidence_refs: list[str] | None = None
    risk_ref: str | None = None


class PolicyWrite(EnvelopeWrite):
    name: str
    status: DocumentStatus
    version: str | None = None
    adopted: date | None = None
    reviewed: date | None = None
    review_interval: str | None = None
    owner_ref: str | None = None
    control_refs: list[str] | None = None


class ProcedureWrite(EnvelopeWrite):
    name: str
    status: DocumentStatus
    policy_ref: str | None = None
    control_refs: list[str] | None = None
    interval: str | None = None
    owner_ref: str | None = None


class RiskWrite(EnvelopeWrite):
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


class ExceptionWrite(EnvelopeWrite):
    implementation_ref: str
    justification: str
    expires: date
    approver_ref: str
    risk_ref: str | None = None


class MappingReviewWrite(EnvelopeWrite):
    mapping_ref: str
    review_status: Literal["reviewed", "rejected"]
    summary: str | None = None


# --- query models ------------------------------------------------------------------------


class Listing(PageRequest):
    revoked: bool = False


class FrameworkQuery(PageRequest):
    pass


class RequirementQuery(Listing):
    framework_id: str | None = None
    class_: RequirementClass | None = Field(default=None, alias="class")
    q: str | None = None
    withdrawn: bool = False


class ControlQuery(Listing):
    origin: Origin | None = None
    family: str | None = None
    q: str | None = None


class MappingQuery(Listing):
    source_id: str | None = None
    target_id: str | None = None
    relationship: Relationship | None = None
    review_status: Literal["draft", "reviewed"] | None = None


class BaselineQuery(Listing):
    extends_id: str | None = None


class TestQuery(Listing):
    __test__ = False

    control_id: str | None = None
    method: Literal["automated", "manual"] | None = None
    required: bool | None = None


class PartyQuery(Listing):
    kind: Literal["person", "team", "role", "organization"] | None = None
    q: str | None = None


class ComponentQuery(Listing):
    kind: Literal["infrastructure", "software", "people", "data", "procedure", "service"] | None = (
        None
    )
    provider_id: str | None = None


class SystemQuery(Listing):
    q: str | None = None


class ProgramQuery(Listing):
    system_id: str | None = None


class ImplementationQuery(Listing):
    system_id: str | None = None
    control_id: str | None = None
    component_id: str | None = None
    status: ImplementationStatus | None = None
    responsibility: Responsibility | None = None
    origin: Literal["organization", "provider"] | None = None


class ScopedImplementationQuery(PageRequest):
    system_id: str | None = None


class ResultQuery(PageRequest):
    test_id: str | None = None
    implementation_id: str | None = None
    outcome: Literal["pass", "fail", "error", "skip"] | None = None
    observed_after: datetime | None = None


class OutcomeQuery(PageRequest):
    outcome: Literal["pass", "fail", "error", "skip"] | None = None


class EvidenceQuery(Listing):
    implementation_id: str | None = None
    result_id: str | None = None
    method: EvidenceMethod | None = None
    valid_on: date | None = None


class ValidOnQuery(PageRequest):
    valid_on: date | None = None


class FindingQuery(Listing):
    system_id: str | None = None
    determination: Literal["satisfied", "not-satisfied"] | None = None
    objective: str | None = None


class PolicyQuery(Listing):
    status: DocumentStatus | None = None
    control_id: str | None = None


class ProcedureQuery(Listing):
    policy_id: str | None = None
    status: DocumentStatus | None = None


class RiskQuery(Listing):
    system_id: str | None = None
    status: Literal["open", "treating", "accepted", "closed"] | None = None
    treatment: Literal["mitigate", "accept", "transfer", "avoid"] | None = None
    control_id: str | None = None


class ExceptionQuery(Listing):
    implementation_id: str | None = None
    expires_before: date | None = None


class MappingReviewQuery(Listing):
    mapping_id: str | None = None
    review_status: Literal["reviewed", "rejected"] | None = None


# --- matchers ------------------------------------------------------------------------------


def _eq(expected: Any, actual: Any) -> bool:
    return expected is None or expected == actual


def _contains(needle: str | None, *haystack: str | None) -> bool:
    return needle is None or needle.lower() in " ".join(h or "" for h in haystack).lower()


def _has(expected: str | None, values: list[str] | None) -> bool:
    return expected is None or expected in (values or [])


def valid_on(evidence: Evidence, day: date | None) -> bool:
    if day is None:
        return True
    return (evidence.valid_from is None or evidence.valid_from <= day) and (
        evidence.valid_until is None or day <= evidence.valid_until
    )


def _requirement(row: Row, q: RequirementQuery) -> bool:
    r: Requirement = row.obj  # type: ignore[assignment]
    return (
        _eq(q.framework_id, r.framework_ref)
        and _eq(q.class_, r.class_)
        and _contains(q.q, r.name, r.display_id)
        and (q.withdrawn or not r.is_withdrawn)
    )


def _control(row: Row, q: ControlQuery) -> bool:
    c: Control = row.obj  # type: ignore[assignment]
    return (
        _eq(q.origin, c.origin)
        and _eq(q.family, c.family)
        and _contains(q.q, c.name, c.display_id, c.statement)
    )


def _mapping(row: Row, q: MappingQuery) -> bool:
    m: Mapping = row.obj  # type: ignore[assignment]
    target_ok = q.target_id is None or (
        m.target_ref == q.target_id if "#" in q.target_id else ids.base(m.target_ref) == q.target_id
    )
    return (
        _eq(q.source_id, m.source_ref)
        and target_ok
        and _eq(q.relationship, m.relationship)
        and _eq(q.review_status, m.review_status or "draft")
    )


def _test(row: Row, q: TestQuery) -> bool:
    t: Test = row.obj  # type: ignore[assignment]
    return (
        _eq(q.control_id, t.control_ref)
        and _eq(q.method, t.method)
        and (q.required is None or bool(t.required) == q.required)
    )


def _component(row: Row, q: ComponentQuery) -> bool:
    c: Component = row.obj  # type: ignore[assignment]
    provider_ok = q.provider_id is None or row.source == PROVIDER_PREFIX + q.provider_id
    return _eq(q.kind, c.kind) and provider_ok


def _implementation(row: Row, q: ImplementationQuery) -> bool:
    i: Implementation = row.obj  # type: ignore[assignment]
    return (
        _eq(q.system_id, i.system_ref)
        and _eq(q.control_id, i.control_ref)
        and _eq(q.component_id, i.component_ref)
        and _eq(q.status, i.status)
        and _eq(q.responsibility, i.responsibility)
        and _eq(q.origin, i.origin or "organization")
    )


def _result(row: Row, q: ResultQuery) -> bool:
    r: Result = row.obj  # type: ignore[assignment]
    return (
        _eq(q.test_id, r.test_ref)
        and _eq(q.implementation_id, r.implementation_ref)
        and _eq(q.outcome, r.outcome)
        and (q.observed_after is None or r.observed > q.observed_after)
    )


def _evidence(row: Row, q: EvidenceQuery) -> bool:
    e: Evidence = row.obj  # type: ignore[assignment]
    return (
        _eq(q.implementation_id, e.implementation_ref)
        and _eq(q.result_id, e.result_ref)
        and _eq(q.method, e.method)
        and valid_on(e, q.valid_on)
    )


def _risk(row: Row, q: RiskQuery) -> bool:
    r: Risk = row.obj  # type: ignore[assignment]
    return (
        _eq(q.system_id, r.system_ref)
        and _eq(q.status, r.status)
        and _eq(q.treatment, r.treatment)
        and _has(q.control_id, r.control_refs)
    )


# --- server-owned fields ---------------------------------------------------------------------


async def _prepare_control(body: dict[str, Any], ctx: WriteContext) -> dict[str, Any]:
    return {**body, "origin": Origin.CUSTOM.value}


async def _prepare_implementation(body: dict[str, Any], ctx: WriteContext) -> dict[str, Any]:
    if body.get("origin", "organization") != "organization":
        raise Invalid(
            "provider rows arrive through POST /providers",
            errors=[FieldError("origin provider is not written here", "/origin")],
        )
    return {k: v for k, v in body.items() if k != "origin"}


async def _prepare_result(body: dict[str, Any], ctx: WriteContext) -> dict[str, Any]:
    test = ctx.graph.test(body.get("test_ref"))
    if test is not None and test.method != "manual":
        raise Invalid(
            "a harness run records the results of an automated test; use POST /tests/{id}/runs",
            errors=[FieldError("this route records the outcome of a manual test", "/test_ref")],
        )
    return body


async def _prepare_evidence(body: dict[str, Any], ctx: WriteContext) -> dict[str, Any]:
    """Complete evidence keeps `resource`, `method`, dates, and refs (RFC 0001 section 7.14)."""
    old = ctx.old
    if not (isinstance(old, Evidence) and old.complete):
        return body
    envelope = {k: v for k, v in old.body().items() if k in (*SERVER_FIELDS, "id")}
    try:
        candidate = Evidence.model_validate({**body, **envelope})
    except ValidationError:
        return body  # the schema check reports it
    changed = [f for f in EVIDENCE_FROZEN if getattr(candidate, f) != getattr(old, f)]
    if changed:
        raise Conflict(
            f"complete evidence does not change {', '.join(changed)}; revoke it and record new",
            slug="evidence-complete",
        )
    return body


async def _prepare_document(body: dict[str, Any], ctx: WriteContext) -> dict[str, Any]:
    """`resource` is set by the content route, never by the body."""
    body = {k: v for k, v in body.items() if k != "resource"}
    if ctx.old is not None and getattr(ctx.old, "resource", None) is not None:
        body["resource"] = ctx.old.resource.model_dump(mode="json", exclude_none=True)  # type: ignore[attr-defined]
    return body


async def _prepare_review(body: dict[str, Any], ctx: WriteContext) -> dict[str, Any]:
    if ctx.old is not None and body.get("mapping_ref") != ctx.old.mapping_ref:  # type: ignore[attr-defined]
        raise Invalid(errors=[FieldError("mapping_ref cannot change", "/mapping_ref")])
    row = await ctx.store.get(body["mapping_ref"]) if body.get("mapping_ref") else None
    if row is None or row.obj.type != "mapping":
        raise Invalid(
            errors=[FieldError("mapping_ref does not resolve to a mapping", "/mapping_ref")]
        )
    if row.source != LIBRARY:
        raise Invalid(
            errors=[
                FieldError(
                    "a mapping review is for a library mapping; edit an organization mapping",
                    "/mapping_ref",
                )
            ]
        )
    if ctx.old is not None and "review_status" not in (ctx.patch or {}):
        # Editing the summary is not a review of the current body (RFC 0002 section 6).
        return {
            **body,
            "library_version": ctx.old.library_version,  # type: ignore[attr-defined]
            "mapping_modified": ctx.old.mapping_modified,
        }  # type: ignore[attr-defined]
    pin = await ctx.store.library_pin()  # type: ignore[attr-defined]
    return {
        **body,
        "library_version": pin.version if pin else "unpinned",
        "mapping_modified": row.obj.modified,
    }


# --- agent gates and extra permissions (RFC 0003 section 4) -------------------------------------


def _impl_gate(new: Envelope, old: Envelope | None) -> str | None:
    if new.status != "planned":  # type: ignore[attr-defined]
        return "an agent drafts implementations as planned; a person marks them otherwise"
    return None


def _impl_extra(new: Envelope, old: Envelope | None) -> list[P]:
    return [P.IMPLEMENTATIONS_ATTEST] if new.status != "planned" else []  # type: ignore[attr-defined]


def _mapping_reviewed(m: Envelope) -> bool:
    return m.review_status == "reviewed" or bool(m.combined_with_refs)  # type: ignore[attr-defined]


def _mapping_gate(new: Envelope, old: Envelope | None) -> str | None:
    if _mapping_reviewed(new):
        return (
            "an agent drafts mappings; review_status reviewed and combined_with_refs are a person's"
        )
    return None


def _run_changed(new: Envelope, old: Envelope | None) -> bool:
    run = new.run  # type: ignore[attr-defined]
    return run is not None and (old is None or old.run != run)  # type: ignore[attr-defined]


def _test_gate(new: Envelope, old: Envelope | None) -> str | None:
    if _run_changed(new, old) or (old is not None and old.run != new.run):  # type: ignore[attr-defined]
        return "an agent does not write or change a run block"
    return None


def _test_extra(new: Envelope, old: Envelope | None) -> list[P]:
    changed = _run_changed(new, old) or (old is not None and old.run != new.run)  # type: ignore[attr-defined]
    return [P.TESTS_DEFINE_RUN] if changed else []


def _doc_gate(new: Envelope, old: Envelope | None) -> str | None:
    return "an agent does not adopt a document" if new.status == "adopted" else None  # type: ignore[attr-defined]


def _doc_extra(new: Envelope, old: Envelope | None) -> list[P]:
    return [P.POLICIES_ADOPT] if new.status == "adopted" else []  # type: ignore[attr-defined]


def _risk_gate(new: Envelope, old: Envelope | None) -> str | None:
    return "an agent does not accept a risk" if new.status == "accepted" else None  # type: ignore[attr-defined]


def _risk_extra(new: Envelope, old: Envelope | None) -> list[P]:
    return [P.RISKS_ACCEPT] if new.status == "accepted" else []  # type: ignore[attr-defined]


def _refuse(reason: str):
    return lambda new, old: reason


# --- the specs --------------------------------------------------------------------------------

FRAMEWORK = TypeSpec(
    "framework", Framework, FrameworkQuery, read_permission=P.LIBRARY_READ, revoke_permission=None
)
REQUIREMENT = TypeSpec(
    "requirement",
    Requirement,
    RequirementQuery,
    read_permission=P.LIBRARY_READ,
    revoke_permission=None,
    matches=_requirement,
)
CONTROL = TypeSpec(
    "control",
    Control,
    ControlQuery,
    ControlWrite,
    P.CONTROLS_READ,
    P.CONTROLS_WRITE,
    P.CONTROLS_REVOKE,
    _control,
    _prepare_control,
)
MAPPING = TypeSpec(
    "mapping",
    Mapping,
    MappingQuery,
    MappingWrite,
    P.CONTROLS_READ,
    P.MAPPINGS_WRITE,
    P.OBJECTS_REVOKE,
    _mapping,
    extra_permissions=lambda n, o: [P.MAPPINGS_REVIEW] if _mapping_reviewed(n) else [],
    agent_gate=_mapping_gate,
)
BASELINE = TypeSpec(
    "baseline",
    Baseline,
    BaselineQuery,
    BaselineWrite,
    P.CONTROLS_READ,
    P.PROGRAMS_WRITE,
    P.OBJECTS_REVOKE,
    lambda row, q: _eq(q.extends_id, row.obj.extends_ref),
)
TEST = TypeSpec(
    "test",
    Test,
    TestQuery,
    TestWrite,
    P.CONTROLS_READ,
    P.TESTS_WRITE,
    P.OBJECTS_REVOKE,
    _test,
    extra_permissions=_test_extra,
    agent_gate=_test_gate,
)
PARTY = TypeSpec(
    "party",
    Party,
    PartyQuery,
    PartyWrite,
    P.PROGRAMS_READ,
    P.SYSTEMS_WRITE,
    P.OBJECTS_REVOKE,
    lambda row, q: _eq(q.kind, row.obj.kind) and _contains(q.q, row.obj.name),
)
COMPONENT = TypeSpec(
    "component",
    Component,
    ComponentQuery,
    ComponentWrite,
    P.PROGRAMS_READ,
    P.SYSTEMS_WRITE,
    P.OBJECTS_REVOKE,
    _component,
)
SYSTEM = TypeSpec(
    "system",
    System,
    SystemQuery,
    SystemWrite,
    P.PROGRAMS_READ,
    P.SYSTEMS_WRITE,
    P.OBJECTS_REVOKE,
    lambda row, q: _contains(q.q, row.obj.name, row.obj.function, row.obj.boundary),
)
PROGRAM = TypeSpec(
    "program",
    Program,
    ProgramQuery,
    ProgramWrite,
    P.PROGRAMS_READ,
    P.PROGRAMS_WRITE,
    P.OBJECTS_REVOKE,
    lambda row, q: _eq(q.system_id, row.obj.system_ref),
)
IMPLEMENTATION = TypeSpec(
    "implementation",
    Implementation,
    ImplementationQuery,
    ImplementationWrite,
    P.PROGRAMS_READ,
    P.IMPLEMENTATIONS_WRITE,
    P.OBJECTS_REVOKE,
    _implementation,
    _prepare_implementation,
    _impl_extra,
    _impl_gate,
)
RESULT = TypeSpec(
    "result",
    Result,
    ResultQuery,
    ResultWrite,
    P.PROGRAMS_READ,
    P.EVIDENCE_WRITE,
    None,
    _result,
    _prepare_result,
)
EVIDENCE = TypeSpec(
    "evidence",
    Evidence,
    EvidenceQuery,
    EvidenceWrite,
    P.PROGRAMS_READ,
    P.EVIDENCE_WRITE,
    P.OBJECTS_REVOKE,
    _evidence,
    _prepare_evidence,
    noun="evidence",
)
FINDING = TypeSpec(
    "finding",
    Finding,
    FindingQuery,
    FindingWrite,
    P.PROGRAMS_READ,
    P.FINDINGS_WRITE,
    P.FINDINGS_WRITE,
    lambda row, q: (
        _eq(q.system_id, row.obj.system_ref)
        and _eq(q.determination, row.obj.determination)
        and _eq(q.objective, row.obj.objective_ref)
    ),
    agent_gate=_refuse("a finding is an assessor's determination; an agent does not record one"),
    agent_may_create=False,
)
POLICY = TypeSpec(
    "policy",
    Policy,
    PolicyQuery,
    PolicyWrite,
    P.PROGRAMS_READ,
    P.POLICIES_WRITE,
    P.OBJECTS_REVOKE,
    lambda row, q: _eq(q.status, row.obj.status) and _has(q.control_id, row.obj.control_refs),
    _prepare_document,
    _doc_extra,
    _doc_gate,
)
PROCEDURE = TypeSpec(
    "procedure",
    Procedure,
    ProcedureQuery,
    ProcedureWrite,
    P.PROGRAMS_READ,
    P.POLICIES_WRITE,
    P.OBJECTS_REVOKE,
    lambda row, q: _eq(q.policy_id, row.obj.policy_ref) and _eq(q.status, row.obj.status),
    _prepare_document,
    _doc_extra,
    _doc_gate,
)
RISK = TypeSpec(
    "risk",
    Risk,
    RiskQuery,
    RiskWrite,
    P.PROGRAMS_READ,
    P.RISKS_WRITE,
    P.OBJECTS_REVOKE,
    _risk,
    extra_permissions=_risk_extra,
    agent_gate=_risk_gate,
)
EXCEPTION = TypeSpec(
    "exception",
    Exception_,
    ExceptionQuery,
    ExceptionWrite,
    P.PROGRAMS_READ,
    P.EXCEPTIONS_APPROVE,
    P.EXCEPTIONS_APPROVE,
    lambda row, q: (
        _eq(q.implementation_id, row.obj.implementation_ref)
        and (q.expires_before is None or row.obj.expires < q.expires_before)
    ),
    agent_gate=_refuse("a waiver is a person's judgment; an agent does not write one"),
    agent_may_create=False,
)
MAPPING_REVIEW = TypeSpec(
    "mapping_review",
    MappingReview,
    MappingReviewQuery,
    MappingReviewWrite,
    P.CONTROLS_READ,
    P.MAPPINGS_REVIEW,
    P.MAPPINGS_REVIEW,
    lambda row, q: (
        _eq(q.mapping_id, row.obj.mapping_ref) and _eq(q.review_status, row.obj.review_status)
    ),
    _prepare_review,
    agent_gate=_refuse("an agent does not review mappings"),
    agent_may_create=False,
    noun="mapping review",
)

SPECS: dict[str, TypeSpec] = {
    spec.type: spec
    for spec in (
        FRAMEWORK,
        REQUIREMENT,
        CONTROL,
        MAPPING,
        BASELINE,
        TEST,
        PARTY,
        COMPONENT,
        SYSTEM,
        PROGRAM,
        IMPLEMENTATION,
        RESULT,
        EVIDENCE,
        FINDING,
        POLICY,
        PROCEDURE,
        RISK,
        EXCEPTION,
        MAPPING_REVIEW,
    )
}
