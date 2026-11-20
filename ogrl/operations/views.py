"""Computed views: shapes the kernel derives and the store never holds.

`EffectiveBaseline`, `ProgramStatus`, `ProgramSummary`, and `Gap` in
api/openapi.yaml. Clients display these. They do not recompute them.
"""

from datetime import datetime

from pydantic import BaseModel

from ogrl.kernel import baselines, status


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


class Connector(BaseModel):
    id: str
    name: str
    description: str | None = None


class DataList[T](BaseModel):
    data: list[T]
