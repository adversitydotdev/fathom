"""Parameter resolution, RFC 0001 sections 7.3 and 7.4."""

import re
from collections.abc import Iterable

from ogrl.kernel import ids
from ogrl.kernel.graph import Graph
from ogrl.kernel.models import Control, Implementation, Mapping

PLACEHOLDER = re.compile(r"\{\{\s*([A-Za-z0-9_]+)\s*\}\}")


def placeholders(text: str | None) -> list[str]:
    return list(dict.fromkeys(PLACEHOLDER.findall(text or "")))


def control_values(
    control: Control,
    implementation: Implementation | None,
    bindings: dict[str, dict[str, str]],
) -> dict[str, str | None]:
    """Implementation value, then the baseline binding, then the control default."""
    names = list(dict.fromkeys([*(control.parameters or {}), *placeholders(control.statement)]))
    own = (implementation.parameter_values or {}) if implementation else {}
    bound = bindings.get(control.id, {})
    values: dict[str, str | None] = {}
    for name in names:
        default = (control.parameters or {}).get(name)
        values[name] = own.get(name) or bound.get(name) or (default.value if default else None)
    return values


def unresolved(
    control: Control,
    implementation: Implementation | None,
    bindings: dict[str, dict[str, str]],
) -> list[str]:
    """Parameters named in the statement that have no value for this program."""
    values = control_values(control, implementation, bindings)
    return [name for name in placeholders(control.statement) if not values.get(name)]


def render(text: str | None, values: dict[str, str | None]) -> str:
    def substitute(match: re.Match[str]) -> str:
        value = values.get(match.group(1))
        return value if value else match.group(0)

    return PLACEHOLDER.sub(substitute, text or "")


def requirement_value(
    graph: Graph,
    requirement_id: str,
    key: str,
    *,
    program_controls: Iterable[str],
    implementations: dict[str, Implementation],
    bindings: dict[str, dict[str, str]],
) -> str | None:
    """One target-framework parameter, RFC 0001 section 7.4.

    `implementations` is the implementation under evaluation per control id.
    Two mappings naming different control parameters for the same key is an
    error, and the parameter stays unset.
    """
    controls = set(program_controls)
    candidates: list[tuple[Mapping, str]] = [
        (m, m.parameter_map[key])
        for m in graph.mappings_by_target.get(requirement_id, [])
        if m.parameter_map and key in m.parameter_map and m.source_ref in controls
    ]
    sources = {
        m.source_ref
        for m in graph.mappings_by_target.get(requirement_id, [])
        if m.source_ref in controls
    }
    for source in sorted(sources):
        impl = implementations.get(source)
        override = (impl.requirement_parameter_values or {}).get(requirement_id, {}) if impl else {}
        if override.get(key):
            return override[key]
    literal = bindings.get(requirement_id, {}).get(key)
    if literal:
        return literal
    if len({(m.source_ref, name) for m, name in candidates}) != 1:
        return None
    mapping, name = candidates[0]
    control = graph.control(mapping.source_ref)
    if control is None:
        return None
    values = control_values(control, implementations.get(control.id), bindings)
    return values.get(name)


def requirement_parameter_keys(graph: Graph, requirement_id: str) -> list[str]:
    requirement = graph.requirement(ids.base(requirement_id))
    return list((requirement.parameters or {}) if requirement else {})
