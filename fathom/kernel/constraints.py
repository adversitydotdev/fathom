"""Graph constraints, RFC 0001 section 7.20.

`check(obj, graph, origin)` returns every violation for one object against a
graph. The graph may hold an older revision of `obj`; it is ignored. A write
calls this before it stores anything, and a restore calls it for every
object of the snapshot. A violation with `conflict=True` is a uniqueness rule
(the API answers 409); every other violation is a 400.
"""

import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import PurePosixPath

from fathom.kernel import ids, rules
from fathom.kernel.graph import Graph, objective_exists, part_ids
from fathom.kernel.models import (
    CONTRIBUTION,
    Baseline,
    Component,
    Control,
    Envelope,
    Evidence,
    Exception_,
    Finding,
    Implementation,
    Mapping,
    MappingReview,
    Origin,
    Policy,
    Procedure,
    Program,
    Result,
    Risk,
    Run,
    System,
    Test,
)

ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
TIMEOUT = re.compile(r"^([1-9][0-9]*)([sm])$")
MAX_TIMEOUT_SECONDS = 60 * 60


@dataclass(frozen=True)
class Violation:
    pointer: str
    detail: str
    conflict: bool = False


def timeout_seconds(value: str | None) -> int:
    """`run.timeout`: a positive integer plus `s` or `m`. Defaults to 5m."""
    if value is None:
        return 300
    match = TIMEOUT.match(value)
    if not match:
        raise ValueError("timeout is a positive integer followed by s or m")
    seconds = int(match.group(1)) * (60 if match.group(2) == "m" else 1)
    if seconds > MAX_TIMEOUT_SECONDS:
        raise ValueError("timeout is at most 60m")
    return seconds


class _Checker:
    def __init__(self, obj: Envelope, graph: Graph, origin: str) -> None:
        self.obj = obj
        self.graph = graph
        self.origin = origin
        self.out: list[Violation] = []

    def fail(self, pointer: str, detail: str, conflict: bool = False) -> None:
        self.out.append(Violation(pointer, detail, conflict))

    def ref(self, pointer: str, value: str | None, *types: str, fragment: bool = False) -> bool:
        if value is None:
            return False
        if not fragment and "#" in value:
            self.fail(pointer, "this reference takes an object id without a fragment")
            return False
        kind = ids.type_of(value)
        if kind is None:
            self.fail(pointer, f"{value} is not an OGRL id")
            return False
        if kind not in types:
            self.fail(pointer, f"{value} must be a {' or '.join(types)}")
            return False
        if self.graph.get(value) is None:
            self.fail(pointer, f"{ids.base(value)} does not resolve")
            return False
        return True

    def refs(self, pointer: str, values: list[str] | None, *types: str) -> None:
        for index, value in enumerate(values or []):
            self.ref(f"{pointer}/{index}", value, *types)

    def objective(self, pointer: str, value: str) -> None:
        if ids.objective_of(value) is None:
            self.fail(pointer, "an objective reference is a requirement id plus #obj.<id>")
        elif not objective_exists(self.graph, value):
            self.fail(pointer, f"{value} does not match an objective on that requirement")

    def others(self, model: type[Envelope]) -> Iterator:
        return (o for o in self.graph.all(model) if o.id != self.obj.id)


def _control(c: _Checker, obj: Control) -> None:
    if c.origin == "organization" and obj.origin is Origin.STANDARD:
        c.fail("/origin", "an organization control has origin custom")


def _mapping(c: _Checker, m: Mapping) -> None:
    for other in c.others(Mapping):  # a member of another mapping's combined set
        if m.id in (other.combined_with_refs or []) and not m.is_revoked:
            if m.target_ref != other.target_ref:
                c.fail("/target_ref", f"this mapping is in the combined set on {other.id}")
            if ids.type_of(m.source_ref) != "control" or m.relationship not in CONTRIBUTION:
                c.fail(
                    "/relationship",
                    f"a member of the combined set on {other.id} is "
                    "a control mapping with subset-of or intersects-with",
                )
    if c.ref("/target_ref", m.target_ref, "requirement", fragment=True):
        frag = ids.fragment(m.target_ref)
        requirement = c.graph.requirement(m.target_ref)
        if frag is not None and requirement is not None and frag not in part_ids(requirement):
            c.fail("/target_ref", f"#{frag} is not a part of {requirement.id}")
    c.ref("/source_ref", m.source_ref, "control", "requirement")
    source_is_control = ids.type_of(m.source_ref) == "control"
    if m.parameter_map:
        if not source_is_control:
            c.fail("/parameter_map", "parameter_map needs a control as source_ref")
        control = c.graph.control(m.source_ref)
        requirement = c.graph.requirement(m.target_ref)
        for key, name in m.parameter_map.items():
            if requirement is not None and key not in (requirement.parameters or {}):
                c.fail(f"/parameter_map/{key}", f"{key} is not a parameter of {requirement.id}")
            if control is not None and name not in (control.parameters or {}):
                c.fail(f"/parameter_map/{key}", f"{name} is not a parameter of {control.id}")
    if m.combined_with_refs:
        if not source_is_control or m.relationship not in CONTRIBUTION:
            c.fail(
                "/combined_with_refs",
                "a combined set has controls as sources and subset-of or intersects-with",
            )
        members = {m.id, *m.combined_with_refs}
        for index, ref in enumerate(m.combined_with_refs):
            pointer = f"/combined_with_refs/{index}"
            if not c.ref(pointer, ref, "mapping"):
                continue
            member = c.graph.typed(ref, Mapping)
            if member is None:
                continue
            if member.target_ref != m.target_ref:
                c.fail(pointer, f"{ref} has a different target_ref")
            if (
                ids.type_of(member.source_ref) != "control"
                or member.relationship not in CONTRIBUTION
            ):
                c.fail(pointer, f"{ref} is not a control mapping with subset-of or intersects-with")
        for other in c.others(Mapping):
            if other.combined_with_refs and members & {other.id, *other.combined_with_refs}:
                c.fail("/combined_with_refs", f"a mapping here is already in the set on {other.id}")
    if c.origin == "organization" and not m.is_revoked:
        for other in c.others(Mapping):
            if other.is_revoked:
                continue
            if (
                c.graph.is_organization(other.id)
                and other.source_ref == m.source_ref
                and other.target_ref == m.target_ref
            ):
                c.fail("/target_ref", f"{other.id} already maps this source and target", True)


def _baseline(c: _Checker, b: Baseline) -> None:
    if b.extends_ref and any(o.extends_ref == b.id for o in c.others(Baseline)):
        c.fail("/extends_ref", "another baseline extends this one; one level deep")
    if b.extends_ref and c.ref("/extends_ref", b.extends_ref, "baseline"):
        base = c.graph.baseline(b.extends_ref)
        if base is not None and base.extends_ref:
            c.fail("/extends_ref", f"{b.extends_ref} extends another baseline; one level deep")
        if b.extends_ref == b.id:
            c.fail("/extends_ref", "a baseline does not extend itself")
    if c.origin == "library" and b.extends_ref:
        c.fail("/extends_ref", "a library baseline has no extends_ref")
    c.refs("/framework_refs", b.framework_refs, "framework")
    for index, ref in enumerate(b.control_refs or []):
        if c.ref(f"/control_refs/{index}", ref, "control") and c.origin == "library":
            control = c.graph.control(ref)
            if control is not None and control.origin is not Origin.STANDARD:
                c.fail(f"/control_refs/{index}", "a library baseline lists standard controls only")
    for index, ref in enumerate(b.requirement_refs or []):
        pointer = f"/requirement_refs/{index}"
        if not c.ref(pointer, ref, "requirement"):
            continue
        requirement = c.graph.requirement(ref)
        if requirement is None:
            continue
        if requirement.is_withdrawn:
            c.fail(pointer, f"{ref} is withdrawn")
        if requirement.framework_ref not in (b.framework_refs or []):
            c.fail(pointer, f"{ref} is not in one of this baseline's framework_refs")
    for key in b.parameter_bindings or {}:
        c.ref(f"/parameter_bindings/{key}", key, "control", "requirement")


def _test(c: _Checker, t: Test) -> None:
    c.ref("/control_ref", t.control_ref, "control")
    for other in c.others(Test):  # tests that fulfill this one constrain it too
        if other.fulfills_ref == t.id and not t.is_revoked:
            if t.fulfills_ref:
                c.fail("/fulfills_ref", f"{other.id} fulfills this test; one level deep")
            if other.control_ref != t.control_ref:
                c.fail("/control_ref", f"{other.id} fulfills this test with another control")
    if t.fulfills_ref and c.ref("/fulfills_ref", t.fulfills_ref, "test"):
        target = c.graph.test(t.fulfills_ref)
        if t.fulfills_ref == t.id:
            c.fail("/fulfills_ref", "a test does not fulfill itself")
        elif target is not None:
            if target.control_ref != t.control_ref:
                c.fail("/fulfills_ref", "fulfills_ref points at a test with the same control_ref")
            if target.fulfills_ref:
                c.fail("/fulfills_ref", f"{target.id} fulfills another test; one level deep")
    if t.system_refs and c.origin != "organization":
        c.fail("/system_refs", "library and provider tests do not set system_refs")
    c.refs("/system_refs", t.system_refs, "system")
    for index, ref in enumerate(t.objective_refs or []):
        c.objective(f"/objective_refs/{index}", ref)
    c.ref("/procedure_ref", t.procedure_ref, "procedure")
    if t.run is None:
        return
    if t.method == "manual":
        c.fail("/run", "a manual test has no run block")
    _run_fields(c, t.run)
    try:
        timeout_seconds(t.run.timeout)
    except ValueError as exc:
        c.fail("/run/timeout", str(exc))
    for index, name in enumerate(t.run.env or []):
        if not ENV_NAME.match(name):
            c.fail(f"/run/env/{index}", "env lists variable names, not values")
    for index, item in enumerate(t.run.evidence or []):
        path = PurePosixPath(item.path)
        if path.is_absolute() or ".." in path.parts or item.path.startswith("\\"):
            c.fail(f"/run/evidence/{index}/path", "a relative path with no ..")


# Fields each runner reads. An unrecognized runner is preserved unchecked (RFC 0001 7.6).
RUN_FIELDS: dict[str, frozenset[str]] = {
    "shell": frozenset({"command", "timeout", "env", "evidence"}),
    "rule": frozenset({"source", "select", "assert", "aggregate", "subject", "allow_empty"}),
    "integration": frozenset({"check", "sources", "with", "timeout"}),
}
ALL_RUN_FIELDS = frozenset().union(*RUN_FIELDS.values())


def _run_fields(c: _Checker, run: Run) -> None:
    allowed = RUN_FIELDS.get(run.runner)
    if allowed is None:
        return
    present = {k for k, v in run.model_dump(by_alias=True).items() if v is not None}
    for name in sorted((present & ALL_RUN_FIELDS) - allowed):
        c.fail(f"/run/{name}", f"runner {run.runner} does not take {name}")
    if run.runner == "shell" and not run.command:
        c.fail("/run/command", "runner shell requires command")
    if run.runner == "rule":
        for pointer, message in rules.rule_errors(run):
            c.fail(pointer, message)
    if run.runner == "integration":
        check: rules.Reference | None = None
        if not run.check:
            c.fail("/run/check", "runner integration requires check")
        else:
            try:
                check = rules.parse_reference(run.check)
            except ValueError as exc:
                c.fail("/run/check", str(exc))
        if not run.sources:
            c.fail("/run/sources", "runner integration requires at least one source")
        for index, text in enumerate(run.sources or []):
            try:
                source = rules.parse_reference(text)
            except ValueError as exc:
                c.fail(f"/run/sources/{index}", str(exc))
                continue
            if check is not None and source.integration != check.integration:
                c.fail(f"/run/sources/{index}", f"a source of {check.integration}, as the check")
        if len(set(run.sources or [])) != len(run.sources or []):
            c.fail("/run/sources", "each source is listed once")


def _component(c: _Checker, obj: Component) -> None:
    c.ref("/party_ref", obj.party_ref, "party")


def _system(c: _Checker, s: System) -> None:
    c.refs("/component_refs", s.component_refs, "component")
    own = set(s.component_refs or [])
    for i, info in enumerate(s.information_types or []):
        for j, ref in enumerate(info.component_refs or []):
            if ref not in own:
                c.fail(
                    f"/information_types/{i}/component_refs/{j}",
                    "not one of the system's components",
                )
    for i, party in enumerate(s.parties or []):
        c.ref(f"/parties/{i}/party_ref", party.party_ref, "party")
        if party.authorization is not None and party.role != "subservice":
            c.fail(f"/parties/{i}/authorization", "authorization belongs on a subservice party")


def _program(c: _Checker, p: Program) -> None:
    c.ref("/system_ref", p.system_ref, "system")
    c.ref("/baseline_ref", p.baseline_ref, "baseline")


def _implementation(c: _Checker, i: Implementation) -> None:
    if not (i.system_ref or i.component_ref):
        c.fail("/system_ref", "an implementation has system_ref, component_ref, or both")
    if not (i.control_ref or i.requirement_ref):
        c.fail("/control_ref", "an implementation has control_ref, requirement_ref, or both")
    c.ref("/system_ref", i.system_ref, "system")
    c.ref("/component_ref", i.component_ref, "component")
    c.ref("/control_ref", i.control_ref, "control")
    c.ref("/requirement_ref", i.requirement_ref, "requirement")
    c.ref("/owner_ref", i.owner_ref, "party")
    c.ref("/subservice_ref", i.subservice_ref, "party")
    if i.responsibility == "subservice" and not i.subservice_ref and not i.is_provider:
        c.fail("/subservice_ref", "responsibility subservice names the party in subservice_ref")
    # OGRL provider bundles (control_ref). OSCAL imports speak via requirement_ref and may omit.
    if (
        i.is_provider
        and i.control_ref
        and i.responsibility in ("shared", "customer")
        and not i.customer_responsibility
    ):
        c.fail(
            "/customer_responsibility",
            f"responsibility {i.responsibility} on a provider row includes customer_responsibility",
        )
    if i.is_revoked or not i.control_ref:
        return
    for other in c.others(Implementation):
        if other.control_ref != i.control_ref:
            continue
        same = (
            other.system_ref == i.system_ref
            and other.component_ref == i.component_ref
            and (i.system_ref is not None or i.component_ref is not None)
        )
        if same:
            c.fail("/control_ref", f"{other.id} already implements this control here", True)


def _result(c: _Checker, r: Result) -> None:
    test_ok = c.ref("/test_ref", r.test_ref, "test")
    impl_ok = c.ref("/implementation_ref", r.implementation_ref, "implementation")
    if test_ok and impl_ok:
        test = c.graph.test(r.test_ref)
        impl = c.graph.implementation(r.implementation_ref)
        if test and impl and test.control_ref != impl.control_ref:
            c.fail(
                "/implementation_ref", "the test's control and the implementation's control differ"
            )
    for index, ref in enumerate(r.objective_refs or []):
        c.objective(f"/objective_refs/{index}", ref)
    c.refs("/evidence_refs", r.evidence_refs, "evidence")


def _finding(c: _Checker, f: Finding) -> None:
    c.ref("/system_ref", f.system_ref, "system")
    c.objective("/objective_ref", f.objective_ref)
    c.ref("/implementation_ref", f.implementation_ref, "implementation")
    c.refs("/evidence_refs", f.evidence_refs, "evidence")
    c.ref("/risk_ref", f.risk_ref, "risk")


def _evidence(c: _Checker, e: Evidence) -> None:
    if not (e.implementation_ref or e.result_ref):
        c.fail("/implementation_ref", "evidence has implementation_ref, result_ref, or both")
    c.ref("/implementation_ref", e.implementation_ref, "implementation")
    c.ref("/result_ref", e.result_ref, "result")
    if e.valid_from and e.valid_until and e.valid_until < e.valid_from:
        c.fail("/valid_until", "valid_until is before valid_from")


def _document(c: _Checker, d: Policy | Procedure) -> None:
    c.ref("/owner_ref", d.owner_ref, "party")
    c.refs("/control_refs", d.control_refs, "control")
    if d.status == "adopted":
        if d.resource is None or d.resource.digest is None:
            c.fail(
                "/status", "an adopted document requires resource.digest; upload its content first"
            )
        if not d.owner_ref:
            c.fail("/owner_ref", "an adopted document requires owner_ref")
        if isinstance(d, Policy) and d.adopted is None:
            c.fail("/adopted", "an adopted policy requires the adopted date")
    if isinstance(d, Procedure):
        c.ref("/policy_ref", d.policy_ref, "policy")


def _risk(c: _Checker, r: Risk) -> None:
    c.ref("/system_ref", r.system_ref, "system")
    c.ref("/owner_ref", r.owner_ref, "party")
    c.ref("/approver_ref", r.approver_ref, "party")
    c.refs("/control_refs", r.control_refs, "control")
    if r.status == "accepted":
        if r.treatment != "accept":
            c.fail("/treatment", "status accepted requires treatment accept")
        if not r.approver_ref:
            c.fail("/approver_ref", "status accepted requires approver_ref")
        if r.review_on is None:
            c.fail("/review_on", "status accepted requires review_on")
    for index, milestone in enumerate(r.milestones or []):
        if milestone.done is not None and milestone.done < r.created.date():
            c.fail(f"/milestones/{index}/done", "done is on or after the risk's created date")


def _exception(c: _Checker, e: Exception_) -> None:
    if c.ref("/implementation_ref", e.implementation_ref, "implementation"):
        target = c.graph.implementation(e.implementation_ref)
        if target is not None and (target.is_provider or not c.graph.is_organization(target.id)):
            c.fail(
                "/implementation_ref",
                "an exception waives an organization implementation; write one for the system",
            )
    c.ref("/approver_ref", e.approver_ref, "party")
    c.ref("/risk_ref", e.risk_ref, "risk")


def _mapping_review(c: _Checker, r: MappingReview) -> None:
    c.ref("/mapping_ref", r.mapping_ref, "mapping")
    if r.is_revoked:
        return
    for other in c.others(MappingReview):
        if other.mapping_ref == r.mapping_ref:
            c.fail("/mapping_ref", f"{other.id} already reviews this mapping", True)


CHECKS: dict[type[Envelope], Callable[[_Checker, Envelope], None]] = {
    Control: _control,
    Mapping: _mapping,
    Baseline: _baseline,
    Test: _test,
    Component: _component,
    System: _system,
    Program: _program,
    Implementation: _implementation,
    Result: _result,
    Finding: _finding,
    Evidence: _evidence,
    Policy: _document,
    Procedure: _document,
    Risk: _risk,
    Exception_: _exception,
    MappingReview: _mapping_review,
}


def check(obj: Envelope, graph: Graph, origin: str = "organization") -> list[Violation]:
    """`origin` is where the object is stored: organization, library, or provider."""
    checker = _Checker(obj, graph, origin)
    rule = CHECKS.get(type(obj))
    if rule is not None:
        rule(checker, obj)
    return checker.out
