"""Computed views: shapes the kernel derives and the store never holds.

`EffectiveBaseline`, `ProgramStatus`, `ProgramSummary`, `SprsReport`, and `Gap` in
api/openapi.yaml. Clients display these. They do not recompute them.
"""

from dataclasses import asdict
from datetime import date, datetime

from pydantic import BaseModel

from fathom.kernel import baselines, sprs, status


class EffectiveBaseline(BaseModel):
    baseline_id: str
    extends_id: str | None = None
    framework_ids: list[str]
    control_ids: list[str]
    requirement_ids: list[str]
    parameter_bindings: dict[str, dict[str, str]]

    @classmethod
    def of(cls, value: baselines.EffectiveBaseline) -> "EffectiveBaseline":
        return cls(**value.__dict__)


class ControlStatus(BaseModel):
    control_id: str
    state: str
    implementation_id: str | None = None
    implementation_ids: list[str] = []
    failed: list[str] = []


class RequirementCoverage(BaseModel):
    requirement_id: str
    state: str
    mapping_ids: list[str] = []
    unmet_control_ids: list[str] | None = None


class ProgramStatus(BaseModel):
    program_id: str
    at: datetime
    controls: list[ControlStatus]
    requirements: list[RequirementCoverage]

    @classmethod
    def of(cls, value: status.ProgramStatus) -> "ProgramStatus":
        return cls(
            program_id=value.program_id,
            at=value.at,
            controls=[ControlStatus(**c.__dict__) for c in value.controls],
            requirements=[
                RequirementCoverage(
                    **{**r.__dict__, "unmet_control_ids": r.unmet_control_ids or None}
                )
                for r in value.requirements
            ],
        )


class ControlCounts(BaseModel):
    met: int
    gap: int
    waived: int
    out_of_scope: int


class RequirementCounts(BaseModel):
    covered: int
    contribution: int
    unmapped: int
    gap: int


class ProgramSummary(BaseModel):
    program_id: str
    at: datetime
    controls: ControlCounts
    requirements: RequirementCounts
    failing_tests: int
    open_risks: int
    expiring_evidence: int
    expiring_exceptions: int
    open_findings: int

    @classmethod
    def of(cls, value: status.ProgramSummary) -> "ProgramSummary":
        return cls(
            **{
                **value.__dict__,
                "controls": ControlCounts(**value.controls),
                "requirements": RequirementCounts(**value.requirements),
            }
        )


class SprsReason(BaseModel):
    code: str
    detail: str


class PoamItem(BaseModel):
    requirement_id: str
    practice_id: str
    state: str
    points: int
    partial: bool
    eligible: bool
    reasons: list[SprsReason]
    due: date | None = None
    risk_ids: list[str]


class Conditional(BaseModel):
    status_date: date
    expires: date
    expired: bool
    days_remaining: int


class Poam(BaseModel):
    required: bool
    eligible: bool
    reasons: list[SprsReason]
    items: list[PoamItem]
    conditional: Conditional | None = None


class Reminder(BaseModel):
    kind: str
    state: str
    due: date | None = None
    days_until: int | None = None
    last: date | None = None


class Reminders(BaseModel):
    reassessment: Reminder
    affirmation: Reminder
    affirming_official: str | None = None
    assessment_type: str | None = None
    assessment_cadence: str | None = None


class SprsReport(BaseModel):
    program_id: str
    at: datetime
    max_score: int
    score: int
    assessable: bool
    assessable_reason: str | None = None
    met: int
    not_met: int
    poam: Poam
    reminders: Reminders
    notes: list[str]

    @classmethod
    def of(cls, value: sprs.SprsReport) -> "SprsReport":
        return cls.model_validate(asdict(value))


class Gap(BaseModel):
    program_id: str
    control_id: str
    implementation_id: str | None = None
    failed: list[str]


class SystemGaps(BaseModel):
    at: datetime
    gaps: list[Gap]


class Health(BaseModel):
    status: str
    version: str


class DataList[T](BaseModel):
    data: list[T]
