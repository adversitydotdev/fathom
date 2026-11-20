"""The walk an SSP render performs, RFC 0001 section 8.1. Shared by both renderers."""

from dataclasses import dataclass, field

from ogrl.kernel import status
from ogrl.kernel.graph import Graph
from ogrl.kernel.models import (
    Control,
    Evidence,
    Exception_,
    Finding,
    Implementation,
    Policy,
    Procedure,
    Result,
    Risk,
    System,
)
from ogrl.kernel.parameters import control_values, render
from ogrl.plugins.ports import RenderRequest


@dataclass
class ControlEntry:
    control: Control
    status: status.ControlStatus
    statement: str
    implementations: list[Implementation]
    latest_results: list[Result]
    evidence: list[Evidence]
    exceptions: list[Exception_]


@dataclass
class Walk:
    graph: Graph
    evaluator: status.Evaluator
    system: System | None
    controls: list[ControlEntry]
    findings: list[Finding]
    policies: list[Policy]
    procedures: list[Procedure]
    risks: list[Risk]
    requirements: list[status.RequirementCoverage] = field(default_factory=list)


def walk(request: RenderRequest) -> Walk:
    graph, program = request.graph, request.program
    evaluator = status.Evaluator(graph, program, request.at)
    evaluated = evaluator.evaluate(request.framework_id)
    by_control = {c.control_id: c for c in evaluated.controls}
    entries: list[ControlEntry] = []
    for control_id in evaluator.baseline.control_ids:
        control = graph.control(control_id)
        if control is None:
            continue
        evaluation = evaluator.under_evaluation(control_id)
        impls = [*evaluation.implementations, *evaluation.provider_halves]
        primary = impls[0] if impls else None
        values = control_values(control, primary, evaluator.baseline.parameter_bindings)
        latest: list[Result] = []
        for test in graph.tests_by_control.get(control_id, []):
            if not (test.required and evaluator.applies(test)):
                continue
            for impl in impls:
                results = [
                    r
                    for r in graph.results_by_pair.get((test.id, impl.id), [])
                    if r.observed <= evaluator.at
                ]
                if results:
                    latest.append(max(results, key=lambda r: r.observed))
        evidence = [
            e
            for impl in impls
            for e in graph.evidence_by_implementation.get(impl.id, [])
            if evaluator.evidence_valid(e)
        ]
        exceptions = [
            e for impl in impls for e in graph.exceptions_by_implementation.get(impl.id, [])
        ]
        entries.append(
            ControlEntry(
                control,
                by_control[control_id],
                render(control.statement, values),
                impls,
                latest,
                evidence,
                exceptions,
            )
        )
    controls = set(evaluator.baseline.control_ids)
    return Walk(
        graph=graph,
        evaluator=evaluator,
        system=graph.system(program.system_ref),
        controls=entries,
        findings=[f for f in status.findings_in_force(graph, program.system_ref, request.at)],
        policies=[
            p
            for p in graph.all(Policy)
            if p.status == "adopted" and controls & set(p.control_refs or [])
        ],
        procedures=[
            p
            for p in graph.all(Procedure)
            if p.status == "adopted" and controls & set(p.control_refs or [])
        ],
        risks=[
            r
            for r in graph.risks()
            if r.status in ("open", "treating") and controls & set(r.control_refs or [])
        ],
        requirements=evaluated.requirements,
    )
