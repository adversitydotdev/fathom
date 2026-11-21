"""Sources, snapshots, and the `rule` runner, RFC 0001 section 7.6.

Everything here is pure: a rule's outcome is a function of the test's run
block, the concatenated snapshot items, the control parameters, and the
snapshot's `collected` time. No clock and no I/O, so every harness reaches
the same outcome for the same inputs.

CEL comes from `common-expression-language` (bindings over the Rust `cel`
crate). RFC 0005 section 8 moves it into `ogrl-rs` once the CLI grows
`ogrl rule eval`; nothing outside this module imports it.
"""

import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Literal

import cel

SNAPSHOT_MEDIA_TYPE = "application/vnd.ogrl.snapshot+json"

_REFERENCE = re.compile(
    r"^(?P<integration>[a-z0-9-]+(?:\.[a-z0-9-]+)+)/(?P<name>[a-z0-9-]+)@(?P<major>[1-9][0-9]*)$"
)


@dataclass(frozen=True, slots=True)
class Reference:
    """`<integration>/<name>@<major>`: a source, or an integration check."""

    integration: str
    name: str
    major: int

    def __str__(self) -> str:
        return f"{self.integration}/{self.name}@{self.major}"


def parse_reference(text: str) -> Reference:
    match = _REFERENCE.match(text or "")
    if match is None:
        raise ValueError(
            "expected <integration>/<name>@<major>, such as dev.adversity.okta/users@1"
        )
    return Reference(match["integration"], match["name"], int(match["major"]))


# --- CEL ---------------------------------------------------------------------------------------


def _distinct(values: list[Any]) -> list[Any]:
    out: list[Any] = []
    for value in values:
        if value not in out:
            out.append(value)
    return out


def _duplicates(values: list[Any]) -> list[Any]:
    """Elements that occur more than once, each once, in order of first repetition."""
    seen: list[Any] = []
    out: list[Any] = []
    for value in values:
        if value in seen:
            if value not in out:
                out.append(value)
        else:
            seen.append(value)
    return out


_DAYS = re.compile(r"^\s*(\d+)\s*(?:days?)?\s*$", re.IGNORECASE)


def _days(value: str) -> timedelta:
    """`days("90 days")`: control parameters are prose, so rules can compare against them."""
    match = _DAYS.match(value or "")
    if match is None:
        raise ValueError(f"days() expects a value such as '90 days', got {value!r}")
    return timedelta(days=int(match[1]))


def _lower_ascii(value: str) -> str:
    return "".join(chr(ord(c) + 32) if "A" <= c <= "Z" else c for c in value)


FUNCTIONS: dict[str, Callable[..., Any]] = {
    "distinct": _distinct,
    "duplicates": _duplicates,
    "lowerAscii": _lower_ascii,
    "days": _days,
}

ITEM_VARIABLES = frozenset({"item", "snapshot", "params", "observed"})
SET_VARIABLES = frozenset({"items", "snapshot", "params", "observed"})
FIELDS: dict[str, frozenset[str]] = {
    "select": ITEM_VARIABLES,
    "assert": ITEM_VARIABLES,
    "subject": ITEM_VARIABLES,
    "aggregate": SET_VARIABLES,
}


_BINDER = re.compile(r"\.(?:all|exists|exists_one|map|filter)\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*,")


def compile_expression(name: str, source: str) -> Any:
    """Compile one run-block expression. Raises ValueError naming what is wrong."""
    try:
        program = cel.compile(source)
    except Exception as exc:  # the binding raises ValueError; be safe about others
        raise ValueError(str(exc).splitlines()[0]) from exc
    bound = set(_BINDER.findall(source))  # `items.map(u, ...)` reports `u` as a variable
    unknown = sorted(set(program.variables()) - FIELDS[name] - bound)
    if unknown:
        allowed = ", ".join(sorted(FIELDS[name]))
        raise ValueError(f"unknown variable {', '.join(unknown)}; {name} may use {allowed}")
    return program


def expression_errors(run: Any) -> list[tuple[str, str]]:
    """(field, message) for every expression in a rule run block that does not compile."""
    errors = []
    for name in FIELDS:
        source = getattr(run, "assert_" if name == "assert" else name, None)
        if source is None:
            continue
        try:
            compile_expression(name, source)
        except ValueError as exc:
            errors.append((name, str(exc)))
    return errors


# --- Evaluation --------------------------------------------------------------------------------


@dataclass(frozen=True)
class RuleSubject:
    kind: str
    name: str
    external_id: str | None = None


@dataclass(frozen=True)
class RuleOutcome:
    outcome: Literal["pass", "fail", "error"]
    summary: str
    subjects: list[RuleSubject] = field(default_factory=list)


class _RuleError(Exception):
    pass


def _context(variables: Mapping[str, Any]) -> Any:
    ctx = cel.Context()
    for name, function in FUNCTIONS.items():
        ctx.add_function(name, function)
    for name, value in variables.items():
        ctx.add_variable(name, value)
    return ctx


def _run(program: Any, variables: Mapping[str, Any], where: str) -> Any:
    try:
        return program.execute(_context(variables))
    except Exception as exc:
        detail = str(exc) or type(exc).__name__
        if isinstance(exc, KeyError):
            detail = f"no such key {detail}"
        raise _RuleError(f"{where}: {detail}") from exc


def _boolean(program: Any, variables: Mapping[str, Any], where: str) -> bool:
    value = _run(program, variables, where)
    if not isinstance(value, bool):
        raise _RuleError(f"{where}: expected a boolean, got {type(value).__name__}")
    return value


def _string(value: Any) -> str | None:
    if value is None or isinstance(value, (dict, list)):
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _default_subject(kind: str, item: Any, index: int) -> RuleSubject:
    item = item if isinstance(item, dict) else {}
    external_id = _string(item.get("id"))
    name = _string(item.get("name"))
    # RFC 0001 drops absent fields; `subjects[].name` is required, so fall back.
    return RuleSubject(
        kind=kind, name=name or external_id or f"item {index}", external_id=external_id
    )


def _custom_subject(program: Any, variables: Mapping[str, Any], where: str) -> RuleSubject:
    value = _run(program, variables, where)
    if not isinstance(value, dict):
        raise _RuleError(f"{where}: expected a map with kind and name")
    kind, name = value.get("kind"), value.get("name")
    external_id = value.get("external_id")
    if not isinstance(kind, str) or not isinstance(name, str):
        raise _RuleError(f"{where}: kind and name must be strings")
    if external_id is not None and not isinstance(external_id, str):
        raise _RuleError(f"{where}: external_id must be a string")
    return RuleSubject(kind=kind, name=name, external_id=external_id)


def evaluate(
    run: Any,
    items: Sequence[Any],
    parameters: Mapping[str, str],
    observed: datetime,
) -> RuleOutcome:
    """The rule harness contract, RFC 0001 section 7.6, after snapshot selection."""
    try:
        source = parse_reference(run.source)
        programs = {
            name: compile_expression(name, text)
            for name in FIELDS
            if (text := getattr(run, "assert_" if name == "assert" else name, None)) is not None
        }
    except ValueError as exc:
        return RuleOutcome("error", str(exc))
    if "assert" not in programs and "aggregate" not in programs:
        return RuleOutcome("error", "a rule needs assert or aggregate")

    shared = {
        "snapshot": {"items": list(items)},
        "params": dict(parameters),
        "observed": observed,
    }
    try:
        selected: list[tuple[int, Any]] = []
        for index, item in enumerate(items):
            if "select" not in programs or _boolean(
                programs["select"], {**shared, "item": item}, f"select: item {index}"
            ):
                selected.append((index, item))
        if not selected and not run.allow_empty:
            return RuleOutcome("error", f"no items selected from {source}")

        subjects: list[RuleSubject] = []
        failed = 0
        if "assert" in programs:
            for index, item in selected:
                scope = {**shared, "item": item}
                if _boolean(programs["assert"], scope, f"assert: item {index}"):
                    continue
                failed += 1
                if "subject" in programs:
                    subjects.append(
                        _custom_subject(programs["subject"], scope, f"subject: item {index}")
                    )
                else:
                    subjects.append(_default_subject(source.name, item, index))

        aggregate_ok = True
        if "aggregate" in programs:
            aggregate_ok = _boolean(
                programs["aggregate"],
                {**shared, "items": [item for _, item in selected]},
                "aggregate",
            )
    except _RuleError as exc:
        return RuleOutcome("error", str(exc)[:2048])

    total = len(selected)
    summary = f"{total - failed} of {total} selected items pass"
    if not aggregate_ok:
        summary += "; aggregate failed"
    outcome: Literal["pass", "fail"] = "pass" if failed == 0 and aggregate_ok else "fail"
    return RuleOutcome(outcome, summary, subjects)
