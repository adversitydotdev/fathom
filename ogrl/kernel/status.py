"""Computed status, RFC 0001 section 8.

`evaluate(graph, program, at)` is the whole computation. It is a function of
the objects and the instant. Nothing here stores `met`, `gap`, `waived`, or
`out_of_scope`; the API returns these values and clients render them.
"""

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from ogrl.kernel import ids
from ogrl.kernel.baselines import EffectiveBaseline, effective
from ogrl.kernel.graph import Graph, leaf_units, units_reached
from ogrl.kernel.models import (
    FULL_COVERAGE,
    Control,
    Evidence,
    Implementation,
    Mapping,
    Program,
    Test,
)
from ogrl.kernel.parameters import unresolved
from ogrl.kernel.timeutil import FRESHNESS_DAYS, on_or_after, utc

MET, GAP, WAIVED, OUT_OF_SCOPE = "met", "gap", "waived", "out_of_scope"
COVERED, CONTRIBUTION, UNMAPPED = "covered", "contribution", "unmapped"
JOINING = frozenset({"equal-to", "equivalent-to", "subset-of"})


@dataclass
class ControlStatus:
    control_id: str
    state: str
    implementation_id: str | None = None
    failed: list[str] = field(default_factory=list)
    implementation_ids: list[str] = field(default_factory=list)


@dataclass
class RequirementCoverage:
    requirement_id: str
    state: str
    mapping_ids: list[str] = field(default_factory=list)
    unmet_control_ids: list[str] = field(default_factory=list)


@dataclass
class ProgramStatus:
    program_id: str
    at: datetime
    controls: list[ControlStatus]
    requirements: list[RequirementCoverage]


@dataclass
class Evaluation:
    """Implementations under evaluation for one control: the set and the provider's halves."""

    implementations: list[Implementation]
    provider_halves: list[Implementation]


class Evaluator:
    def __init__(self, graph: Graph, program: Program, at: datetime) -> None:
        self.graph = graph
        self.program = program
        self.at = utc(at)
        self.date: date = self.at.date()
        baseline = graph.baseline(program.baseline_ref)
        self.baseline: EffectiveBaseline = (
            effective(graph, baseline)
            if baseline
            else EffectiveBaseline(program.baseline_ref, None, [], [], [], {})
        )
        system = graph.system(program.system_ref)
        self.system_id = program.system_ref
        self.component_ids = list(system.component_refs or []) if system else []
        self._control_status: dict[str, ControlStatus] = {}

    # --- mappings --------------------------------------------------------------------

    def is_reviewed(self, mapping: Mapping) -> bool:
        """`review_status: reviewed`, or a current accepting review. A current rejection wins."""
        current = [
            r
            for r in self.graph.reviews_by_mapping.get(mapping.id, [])
            if r.mapping_modified is not None and utc(r.mapping_modified) == mapping.modified
        ]
        if any(r.review_status == "rejected" for r in current):
            return False
        return mapping.review_status == "reviewed" or any(
            r.review_status == "reviewed" for r in current
        )

    def is_replaced(self, mapping: Mapping) -> bool:
        """A library mapping the organization re-authored for the same pair is shown as replaced."""
        if not self.graph.is_library(mapping.id):
            return False
        return any(
            other.target_ref == mapping.target_ref and self.graph.is_organization(other.id)
            for other in self.graph.mappings_by_source.get(mapping.source_ref, [])
        )

    def counts(self, mapping: Mapping) -> bool:
        return (
            not mapping.is_revoked
            and mapping.relationship != "no-relationship"
            and mapping.source_ref in self._controls
            and self.is_reviewed(mapping)
            and not self.is_replaced(mapping)
        )

    @property
    def _controls(self) -> set[str]:
        return set(self.baseline.control_ids)

    # --- implementations -------------------------------------------------------------

    def _joins(self, implementation: Implementation, control_id: str) -> bool:
        """A provider row that speaks a requirement joins a control through a reviewed mapping."""
        if not (implementation.is_provider and implementation.requirement_ref):
            return False
        if implementation.control_ref:
            return False
        return any(
            ids.base(m.target_ref) == implementation.requirement_ref
            and m.relationship in JOINING
            and self.is_reviewed(m)
            and not self.is_replaced(m)
            for m in self.graph.mappings_by_source.get(control_id, [])
        )

    def under_evaluation(self, control_id: str) -> Evaluation:
        candidates = [
            i
            for i in self.graph.implementations
            if i.control_ref == control_id or self._joins(i, control_id)
        ]
        system_rows = [
            i for i in candidates if i.system_ref == self.system_id and not i.component_ref
        ]
        overrides = {
            i.component_ref: i
            for i in candidates
            if i.system_ref == self.system_id and i.component_ref in self.component_ids
        }
        inherited = [
            i
            for i in candidates
            if i.component_ref in self.component_ids
            and not i.system_ref
            and i.component_ref not in overrides
        ]
        if system_rows:
            halves = [i for i in inherited if i.is_provider and i.responsibility == "shared"]
            return Evaluation([system_rows[0]], halves)
        return Evaluation([*overrides.values(), *inherited], [])

    # --- tests and evidence ------------------------------------------------------------

    def applies(self, test: Test) -> bool:
        return not test.system_refs or self.system_id in test.system_refs

    def evidence_valid(self, evidence: Evidence | None) -> bool:
        return (
            evidence is not None
            and not evidence.is_revoked
            and evidence.complete
            and evidence.valid_until is not None
            and evidence.valid_until >= self.date
        )

    def has_unexpired_evidence(self, implementation: Implementation) -> bool:
        return any(
            self.evidence_valid(e)
            for e in self.graph.evidence_by_implementation.get(implementation.id, [])
        )

    def passing(self, test: Test, implementation: Implementation) -> list[str]:
        """Failures for one test on one implementation. Empty when the test is passing."""
        results = [
            r
            for r in self.graph.results_by_pair.get((test.id, implementation.id), [])
            if r.observed <= self.at
        ]
        if not results:
            return [f"test {test.id} has no result for {implementation.id}"]
        current = max(results, key=lambda r: (r.observed, r.modified))
        if current.outcome != "pass":
            return [f"test {test.id}: current result {current.id} is {current.outcome}"]
        if test.interval == "event-driven":
            if current.valid_until is None or self.at > current.valid_until:
                return [f"test {test.id}: result {current.id} is no longer valid"]
        elif test.interval in FRESHNESS_DAYS and self.at > current.observed + timedelta(
            days=FRESHNESS_DAYS[test.interval]
        ):
            return [f"test {test.id}: result {current.id} is older than its {test.interval} window"]
        return [
            f"evidence {evidence_id} cited by {current.id} is expired, revoked, or incomplete"
            for evidence_id in current.evidence_refs or []
            if not self.evidence_valid(self.graph.evidence(evidence_id))
        ]

    def test_failures(self, control: Control, implementation: Implementation) -> list[str]:
        required = [
            t
            for t in self.graph.tests_by_control.get(control.id, [])
            if t.required and not t.fulfills_ref and self.applies(t)
        ]
        if not required:
            if self.has_unexpired_evidence(implementation):
                return []
            return [f"{implementation.id} has no unexpired evidence and no required test applies"]

        failures: list[str] = []
        for test in required:
            fulfilling = [
                t
                for t in self.graph.fulfillers.get(test.id, [])
                if self.applies(t) and t.control_ref == control.id
            ]
            if fulfilling:
                for t in fulfilling:
                    failures += self.passing(t, implementation)
            elif (
                implementation.is_provider
                and implementation.responsibility in ("provider", "subservice")
                and not self.graph.is_organization(test.id)
            ):
                if not self.has_unexpired_evidence(implementation):
                    failures.append(
                        f"test {test.id}: provider row {implementation.id} "
                        "has no unexpired evidence"
                    )
            elif test.method == "automated" and test.run is None:
                failures.append(f"test {test.id}: no methodology has been defined")
            else:
                failures += self.passing(test, implementation)
        return failures

    # --- one control -------------------------------------------------------------------

    def implementation_failures(self, control: Control, impl: Implementation) -> list[str]:
        failures: list[str] = []
        if impl.status != "implemented":
            failures.append(f"{impl.id}: status is {impl.status}")
        if impl.is_provider and impl.responsibility in ("shared", "customer"):
            failures.append(
                f"{impl.id}: provider responsibility is {impl.responsibility}; "
                "the organization's implementation is missing"
            )
        if not impl.is_provider and impl.responsibility in ("customer", "subservice"):
            failures.append(
                f"{impl.id}: responsibility {impl.responsibility} is not the organization's"
            )
        for name in unresolved(control, impl, self.baseline.parameter_bindings):
            failures.append(f"{impl.id}: parameter {name} has no value")
        failures += self.test_failures(control, impl)
        return failures

    def half_failures(self, half: Implementation) -> list[str]:
        failures: list[str] = []
        if half.status != "implemented":
            failures.append(f"provider's half {half.id}: status is {half.status}")
        for evidence in self.graph.evidence_by_implementation.get(half.id, []):
            if evidence.is_revoked or not evidence.complete:
                continue
            if evidence.valid_until is None or evidence.valid_until < self.date:
                failures.append(f"provider's half {half.id}: evidence {evidence.id} has expired")
        return failures

    def waived(self, impl: Implementation) -> bool:
        return impl.status == "exception" and any(
            on_or_after(e.expires, self.date)
            for e in self.graph.exceptions_by_implementation.get(impl.id, [])
        )

    @staticmethod
    def out_of_scope(impl: Implementation) -> bool:
        return impl.status == "not-applicable" or (
            not impl.is_provider and impl.responsibility in ("customer", "subservice")
        )

    def control_status(self, control_id: str) -> ControlStatus:
        if control_id in self._control_status:
            return self._control_status[control_id]
        status = self._compute(control_id)
        self._control_status[control_id] = status
        return status

    def _compute(self, control_id: str) -> ControlStatus:
        control = self.graph.control(control_id)
        if control is None:
            return ControlStatus(control_id, GAP, failed=[f"control {control_id} is not loaded"])
        evaluation = self.under_evaluation(control_id)
        rows = evaluation.implementations
        if not rows:
            return ControlStatus(
                control_id, GAP, failed=["no implementation on the system or its components"]
            )
        primary = rows[0].id
        all_ids = [i.id for i in rows]
        failures = [f for impl in rows for f in self.implementation_failures(control, impl)]
        halves = [f for half in evaluation.provider_halves for f in self.half_failures(half)]
        if not failures and not halves:
            return ControlStatus(control_id, MET, primary, [], all_ids)
        if all(self.waived(i) for i in rows):
            return ControlStatus(control_id, WAIVED, primary, [], all_ids)
        if all(self.out_of_scope(i) for i in rows):
            return ControlStatus(control_id, OUT_OF_SCOPE, primary, [], all_ids)
        return ControlStatus(control_id, GAP, primary, failures + halves, all_ids)

    # --- requirement coverage ------------------------------------------------------------

    def coverage(self, requirement_id: str) -> RequirementCoverage | None:
        requirement = self.graph.requirement(requirement_id)
        if requirement is None or requirement.is_revoked or requirement.is_withdrawn:
            return None
        units = leaf_units(requirement)
        counted = {
            m.id: m for m in self.graph.mappings_by_target.get(requirement.id, []) if self.counts(m)
        }
        mapping_ids = sorted(counted)
        if not any(units_reached(requirement, m.target_ref) for m in counted.values()):
            return RequirementCoverage(requirement.id, UNMAPPED, mapping_ids)

        paths: dict[str, list[frozenset[str]]] = {u: [] for u in units}
        for mapping in counted.values():
            if mapping.relationship in FULL_COVERAGE:
                for unit in units_reached(requirement, mapping.target_ref):
                    paths[unit].append(frozenset({mapping.source_ref}))
            if mapping.combined_with_refs:
                members = [mapping.id, *mapping.combined_with_refs]
                if all(
                    m in counted and counted[m].target_ref == mapping.target_ref for m in members
                ):
                    sources = frozenset(counted[m].source_ref for m in members)
                    for unit in units_reached(requirement, mapping.target_ref):
                        paths[unit].append(sources)

        if any(not paths[u] for u in units):
            return RequirementCoverage(requirement.id, CONTRIBUTION, mapping_ids)

        def holds(path: frozenset[str]) -> bool:
            return all(self.control_status(c).state == MET for c in path)

        failing_units = [u for u in units if not any(holds(p) for p in paths[u])]
        if failing_units:
            unmet = sorted(
                {
                    c
                    for u in failing_units
                    for p in paths[u]
                    for c in p
                    if self.control_status(c).state != MET
                }
            )
            return RequirementCoverage(requirement.id, GAP, mapping_ids, unmet)
        return RequirementCoverage(requirement.id, COVERED, mapping_ids)

    # --- the whole program ---------------------------------------------------------------

    def evaluate(self, framework_id: str | None = None) -> ProgramStatus:
        controls = [self.control_status(c) for c in self.baseline.control_ids]
        requirements: list[RequirementCoverage] = []
        for requirement_id in self.baseline.requirement_ids:
            requirement = self.graph.requirement(requirement_id)
            if framework_id and (requirement is None or requirement.framework_ref != framework_id):
                continue
            coverage = self.coverage(requirement_id)
            if coverage is not None:
                requirements.append(coverage)
        return ProgramStatus(self.program.id, self.at, controls, requirements)


def evaluate(
    graph: Graph, program: Program, at: datetime, framework_id: str | None = None
) -> ProgramStatus:
    return Evaluator(graph, program, at).evaluate(framework_id)


@dataclass
class ProgramSummary:
    program_id: str
    at: datetime
    controls: dict[str, int]
    requirements: dict[str, int]
    failing_tests: int
    open_risks: int
    expiring_evidence: int
    expiring_exceptions: int
    open_findings: int


def findings_in_force(graph: Graph, system_id: str, at: datetime) -> list:
    """The non-revoked finding with the latest `observed`, per objective (RFC 0001 7.13)."""
    latest: dict[str, object] = {}
    for finding in graph.findings():
        if finding.system_ref != system_id or finding.observed > utc(at).date():
            continue
        held = latest.get(finding.objective_ref)
        if held is None or (finding.observed, finding.modified) > (held.observed, held.modified):  # type: ignore[attr-defined]
            latest[finding.objective_ref] = finding
    return list(latest.values())


def summarize(graph: Graph, program: Program, at: datetime) -> ProgramSummary:
    evaluator = Evaluator(graph, program, at)
    status = evaluator.evaluate()
    control_counts = {MET: 0, GAP: 0, WAIVED: 0, OUT_OF_SCOPE: 0}
    for c in status.controls:
        control_counts[c.state] += 1
    requirement_counts = {COVERED: 0, CONTRIBUTION: 0, UNMAPPED: 0, GAP: 0}
    for r in status.requirements:
        requirement_counts[r.state] += 1

    horizon = evaluator.date + timedelta(days=30)
    implementations = {i for c in status.controls for i in c.implementation_ids}
    failing = 0
    for control_id in evaluator.baseline.control_ids:
        for test in graph.tests_by_control.get(control_id, []):
            if not evaluator.applies(test):
                continue
            for impl_id in implementations:
                results = [
                    r
                    for r in graph.results_by_pair.get((test.id, impl_id), [])
                    if r.observed <= evaluator.at
                ]
                if results and max(results, key=lambda r: r.observed).outcome in ("fail", "error"):
                    failing += 1
    controls = set(evaluator.baseline.control_ids)
    open_risks = sum(
        1
        for r in graph.risks()
        if r.status in ("open", "treating")
        and (
            r.system_ref == program.system_ref
            or (not r.system_ref and controls & set(r.control_refs or []))
        )
    )
    expiring_evidence = sum(
        1
        for impl_id in implementations
        for e in graph.evidence_by_implementation.get(impl_id, [])
        if evaluator.evidence_valid(e) and e.valid_until is not None and e.valid_until <= horizon
    )
    expiring_exceptions = sum(
        1
        for impl_id in implementations
        for e in graph.exceptions_by_implementation.get(impl_id, [])
        if evaluator.date <= e.expires <= horizon
    )
    open_findings = sum(
        1
        for f in findings_in_force(graph, program.system_ref, at)
        if f.determination == "not-satisfied"  # type: ignore[attr-defined]
    )
    return ProgramSummary(
        program_id=program.id,
        at=evaluator.at,
        controls=control_counts,
        requirements=requirement_counts,
        failing_tests=failing,
        open_risks=open_risks,
        expiring_evidence=expiring_evidence,
        expiring_exceptions=expiring_exceptions,
        open_findings=open_findings,
    )
