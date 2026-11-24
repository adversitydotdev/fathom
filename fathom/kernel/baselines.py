"""The effective baseline, RFC 0001 section 7.5."""

from dataclasses import dataclass, field

from fathom.kernel.graph import Graph
from fathom.kernel.models import Baseline


@dataclass(frozen=True)
class EffectiveBaseline:
    baseline_id: str
    extends_id: str | None
    framework_ids: list[str]
    control_ids: list[str]
    requirement_ids: list[str]
    parameter_bindings: dict[str, dict[str, str]] = field(default_factory=dict)


def _ordered_union(*lists: list[str] | None) -> list[str]:
    seen: dict[str, None] = {}
    for items in lists:
        for item in items or []:
            seen.setdefault(item, None)
    return list(seen)


def own_requirements(graph: Graph, baseline: Baseline) -> list[str]:
    """`requirement_refs`, or every live requirement of `framework_refs` when it has none."""
    if baseline.requirement_refs:
        return list(baseline.requirement_refs)
    result: list[str] = []
    for framework_id in baseline.framework_refs or []:
        for requirement in graph.requirements_by_framework.get(framework_id, []):
            if not requirement.is_withdrawn:
                result.append(requirement.id)
    return result


def effective(graph: Graph, baseline: Baseline) -> EffectiveBaseline:
    base = graph.baseline(baseline.extends_ref) if baseline.extends_ref else None
    layers = [b for b in (base, baseline) if b is not None]

    bindings: dict[str, dict[str, str]] = {}
    for layer in layers:  # the extending baseline's value wins, key by key
        for key, values in (layer.parameter_bindings or {}).items():
            bindings.setdefault(key, {}).update(values)

    return EffectiveBaseline(
        baseline_id=baseline.id,
        extends_id=baseline.extends_ref,
        framework_ids=_ordered_union(*(b.framework_refs for b in layers)),
        control_ids=_ordered_union(*(b.control_refs for b in layers)),
        requirement_ids=_ordered_union(*(own_requirements(graph, b) for b in layers)),
        parameter_bindings=bindings,
    )
