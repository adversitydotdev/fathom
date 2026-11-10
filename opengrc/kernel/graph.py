"""A read-only view over a set of objects, indexed the way section 8 walks it.

A graph is built from whatever the caller has: a bundle, a store's current
rows, or the revisions in force at a past instant. `library_ids` and
`provider_ids` name the objects that came from a projection. Section 8 needs
both: an organization mapping replaces a library mapping for the same pair
(RFC 0001 section 7.20), and a provider row's evidence can satisfy a library
test that no organization test fulfills.
"""

from collections import defaultdict
from collections.abc import Iterable
from functools import cached_property
from typing import TypeVar

from opengrc.kernel import ids
from opengrc.kernel.models import (
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
    Program,
    Requirement,
    Result,
    Risk,
    System,
    Test,
)

T = TypeVar("T", bound=Envelope)


class Graph:
    def __init__(
        self,
        objects: Iterable[Envelope],
        library_ids: Iterable[str] = (),
        provider_ids: Iterable[str] = (),
    ) -> None:
        self.objects: dict[str, Envelope] = {o.id: o for o in objects}
        self.library_ids = frozenset(library_ids)
        self.provider_ids = frozenset(provider_ids)

    def __contains__(self, object_id: str) -> bool:
        return object_id in self.objects

    def get(self, object_id: str | None) -> Envelope | None:
        return self.objects.get(ids.base(object_id)) if object_id else None

    def typed(self, object_id: str | None, model: type[T]) -> T | None:
        found = self.get(object_id)
        return found if isinstance(found, model) else None

    def all(self, model: type[T], *, revoked: bool = False) -> list[T]:
        return [
            o
            for o in self._by_type.get(model.model_fields["type"].default, [])
            if revoked or not o.is_revoked
        ]

    def is_library(self, object_id: str) -> bool:
        return object_id in self.library_ids

    def is_organization(self, object_id: str) -> bool:
        return object_id not in self.library_ids and object_id not in self.provider_ids

    @cached_property
    def _by_type(self) -> dict[str, list[Envelope]]:
        index: dict[str, list[Envelope]] = defaultdict(list)
        for o in sorted(self.objects.values(), key=lambda o: o.id):
            index[o.type].append(o)
        return index

    # --- indexes over live objects ---------------------------------------------------

    @cached_property
    def mappings_by_target(self) -> dict[str, list[Mapping]]:
        index: dict[str, list[Mapping]] = defaultdict(list)
        for m in self.all(Mapping):
            index[ids.base(m.target_ref)].append(m)
        return index

    @cached_property
    def mappings_by_source(self) -> dict[str, list[Mapping]]:
        index: dict[str, list[Mapping]] = defaultdict(list)
        for m in self.all(Mapping):
            index[m.source_ref].append(m)
        return index

    @cached_property
    def tests_by_control(self) -> dict[str, list[Test]]:
        index: dict[str, list[Test]] = defaultdict(list)
        for t in self.all(Test):
            index[t.control_ref].append(t)
        return index

    @cached_property
    def fulfillers(self) -> dict[str, list[Test]]:
        index: dict[str, list[Test]] = defaultdict(list)
        for t in self.all(Test):
            if t.fulfills_ref:
                index[t.fulfills_ref].append(t)
        return index

    @cached_property
    def implementations(self) -> list[Implementation]:
        return self.all(Implementation)

    @cached_property
    def results_by_pair(self) -> dict[tuple[str, str], list[Result]]:
        index: dict[tuple[str, str], list[Result]] = defaultdict(list)
        for r in self.all(Result):
            index[(r.test_ref, r.implementation_ref)].append(r)
        return index

    @cached_property
    def evidence_by_implementation(self) -> dict[str, list[Evidence]]:
        index: dict[str, list[Evidence]] = defaultdict(list)
        for e in self.all(Evidence):
            if e.implementation_ref:
                index[e.implementation_ref].append(e)
        return index

    @cached_property
    def exceptions_by_implementation(self) -> dict[str, list[Exception_]]:
        index: dict[str, list[Exception_]] = defaultdict(list)
        for e in self.all(Exception_):
            index[e.implementation_ref].append(e)
        return index

    @cached_property
    def reviews_by_mapping(self) -> dict[str, list[MappingReview]]:
        index: dict[str, list[MappingReview]] = defaultdict(list)
        for r in self.all(MappingReview):
            index[r.mapping_ref].append(r)
        return index

    @cached_property
    def requirements_by_framework(self) -> dict[str, list[Requirement]]:
        index: dict[str, list[Requirement]] = defaultdict(list)
        for r in self.all(Requirement):
            index[r.framework_ref].append(r)
        return index

    # --- typed shortcuts ----------------------------------------------------------------

    def control(self, ref: str | None) -> Control | None:
        return self.typed(ref, Control)

    def requirement(self, ref: str | None) -> Requirement | None:
        return self.typed(ref, Requirement)

    def system(self, ref: str | None) -> System | None:
        return self.typed(ref, System)

    def component(self, ref: str | None) -> Component | None:
        return self.typed(ref, Component)

    def baseline(self, ref: str | None) -> Baseline | None:
        return self.typed(ref, Baseline)

    def program(self, ref: str | None) -> Program | None:
        return self.typed(ref, Program)

    def implementation(self, ref: str | None) -> Implementation | None:
        return self.typed(ref, Implementation)

    def test(self, ref: str | None) -> Test | None:
        return self.typed(ref, Test)

    def evidence(self, ref: str | None) -> Evidence | None:
        return self.typed(ref, Evidence)

    def findings(self) -> list[Finding]:
        return self.all(Finding)

    def risks(self) -> list[Risk]:
        return self.all(Risk)


def part_ids(requirement: Requirement) -> list[str]:
    return [p.id for p in requirement.parts or []]


def leaf_units(requirement: Requirement) -> list[str]:
    """RFC 0001 section 8: the leaf parts. A requirement with no parts is one unit, ``."""
    parts = part_ids(requirement)
    if not parts:
        return [""]
    return [p for p in parts if not any(q.startswith(p + ".") for q in parts)]


def units_reached(requirement: Requirement, target_ref: str) -> list[str]:
    """The units a mapping target reaches: all of them, or those under `#part`."""
    units = leaf_units(requirement)
    frag = ids.fragment(target_ref)
    if frag is None:
        return units
    return [u for u in units if u == frag or u.startswith(frag + ".")]


def objective_exists(graph: Graph, ref: str) -> bool:
    requirement = graph.requirement(ref)
    objective = ids.objective_of(ref)
    if requirement is None or objective is None:
        return False
    return any(o.id == objective for o in requirement.objectives or [])
