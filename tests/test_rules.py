"""The `rule` and `integration` run blocks: validation and rule evaluation (RFC 0001 7.6)."""

from datetime import UTC, datetime

import pytest

from fathom.kernel import constraints, rules
from fathom.kernel.graph import Graph
from fathom.kernel.models import Run, Test, parse
from tests.conftest import C1, STAMP, library_objects

OBSERVED = datetime(2026, 11, 21, tzinfo=UTC)
USERS = "dev.adversity.okta/users@1"


def run(**fields) -> Run:
    return Run.model_validate({"runner": "rule", "source": USERS, **fields})


def test_reference_grammar():
    ref = rules.parse_reference("dev.adversity.github/branch-protection@2")
    assert (ref.integration, ref.name, ref.major, str(ref)) == (
        "dev.adversity.github",
        "branch-protection",
        2,
        "dev.adversity.github/branch-protection@2",
    )
    for bad in [
        "okta/users@1",
        "dev.adversity.okta/users",
        "dev.adversity.okta/Users@1",
        "a.b/c@0",
    ]:
        with pytest.raises(ValueError):
            rules.parse_reference(bad)


def test_run_aliases_round_trip():
    body = {"runner": "integration", "check": "a.b/c@1", "sources": ["a.b/d@1"], "with": {"x": "1"}}
    assert Run.model_validate(body).model_dump(by_alias=True, exclude_none=True) == body
    assert run(**{"assert": "true"}).assert_ == "true"


def test_pass_and_fail_with_default_subjects():
    items = [
        {"id": "u1", "name": "alice@x.com", "status": "ACTIVE", "mfa": True},
        {"id": "u2", "name": "bob@x.com", "status": "ACTIVE", "mfa": False},
        {"id": "u3", "name": "carol@x.com", "status": "DEPROVISIONED", "mfa": False},
    ]
    block = run(select='item.status == "ACTIVE"', **{"assert": "item.mfa"})
    out = rules.evaluate(block, items, {}, OBSERVED)
    assert out.outcome == "fail"
    assert out.summary == "1 of 2 selected items pass"
    assert out.subjects == [rules.RuleSubject("users", "bob@x.com", "u2")]

    out = rules.evaluate(block, items[:1], {}, OBSERVED)
    assert (out.outcome, out.summary, out.subjects) == ("pass", "1 of 1 selected items pass", [])


def test_aggregate_and_duplicates():
    items = [{"id": "1", "e": "A"}, {"id": "2", "e": "b"}, {"id": "3", "e": "a"}]
    block = run(aggregate="items.map(u, u.e.lowerAscii()).duplicates().size() == 0")
    out = rules.evaluate(block, items, {}, OBSERVED)
    assert (out.outcome, out.summary) == ("fail", "3 of 3 selected items pass; aggregate failed")
    assert rules.evaluate(block, items[:2], {}, OBSERVED).outcome == "pass"


def test_empty_selection_is_an_error_unless_allowed():
    block = run(select="false", **{"assert": "true"})
    assert rules.evaluate(block, [{"id": "1"}], {}, OBSERVED).outcome == "error"
    allowed = run(select="false", allow_empty=True, **{"assert": "true"})
    assert rules.evaluate(allowed, [{"id": "1"}], {}, OBSERVED).outcome == "pass"


def test_params_and_observed_drive_age_checks():
    block = run(
        **{"assert": 'observed - timestamp(item.created) <= duration(params.max_hours + "h")'}
    )
    items = [
        {"id": "k1", "created": "2026-11-01T00:00:00Z"},
        {"id": "k2", "created": "2026-01-01T00:00:00Z"},
    ]
    out = rules.evaluate(block, items, {"max_hours": "2160"}, OBSERVED)
    assert out.outcome == "fail"
    assert [s.external_id for s in out.subjects] == ["k2"]


def test_days_reads_prose_parameters():
    block = run(**{"assert": "observed - timestamp(item.rotated) <= days(params.rotation_period)"})
    items = [
        {"id": "a", "rotated": "2026-10-01T00:00:00Z"},
        {"id": "b", "rotated": "2026-01-01T00:00:00Z"},
    ]
    out = rules.evaluate(block, items, {"rotation_period": "90 days"}, OBSERVED)
    assert [s.external_id for s in out.subjects] == ["b"]
    bad = rules.evaluate(block, items, {"rotation_period": "quarterly"}, OBSERVED)
    assert bad.outcome == "error" and "days()" in bad.summary


def test_custom_subject():
    block = run(
        subject='{"kind": "account", "name": item.login, "external_id": item.id}',
        **{"assert": "false"},
    )
    out = rules.evaluate(block, [{"id": "7", "login": "x"}], {}, OBSERVED)
    assert out.subjects == [rules.RuleSubject("account", "x", "7")]


@pytest.mark.parametrize(
    ("fields", "fragment"),
    [
        ({"assert": "item.missing"}, "assert: item 0"),
        ({"assert": '"yes"'}, "expected a boolean"),
        ({"assert": "false", "subject": "1"}, "subject: item 0"),
    ],
)
def test_evaluation_errors_name_the_field_and_item(fields, fragment):
    out = rules.evaluate(run(**fields), [{"id": "1"}], {}, OBSERVED)
    assert out.outcome == "error"
    assert fragment in out.summary


def graph() -> Graph:
    return Graph([parse(o) for o in library_objects()])


def violations(run_block: dict) -> dict[str, str]:
    test = Test.model_validate(
        {
            "id": "test--5b8e1f0a-2c3d-4e5f-8a9b-0c1d2e3f4a5b",
            "created": STAMP,
            "modified": STAMP,
            "name": "rule",
            "control_ref": C1,
            "method": "automated",
            "interval": "daily",
            "run": run_block,
        }
    )
    return {v.pointer: v.detail for v in constraints.check(test, graph())}


def test_valid_rule_and_integration_blocks():
    assert violations({"runner": "rule", "source": USERS, "assert": "item.mfa"}) == {}
    assert (
        violations(
            {
                "runner": "integration",
                "check": "dev.adversity.github/branch-protection@1",
                "sources": ["dev.adversity.github/repositories@1"],
                "with": {"branch": "main"},
            }
        )
        == {}
    )


def test_invalid_blocks():
    found = violations({"runner": "rule", "source": "okta/users", "command": "x"})
    assert set(found) == {"/run/source", "/run/assert", "/run/command"}

    found = violations({"runner": "rule", "source": USERS, "assert": "item.a ==", "select": "x.y"})
    assert set(found) == {"/run/assert", "/run/select"}
    assert "unknown variable x" in found["/run/select"]

    found = violations({"runner": "rule", "source": USERS, "aggregate": "item.a"})
    assert "aggregate may use" in found["/run/aggregate"]

    found = violations(
        {"runner": "integration", "check": "a.b/c@1", "sources": ["x.y/d@1", "x.y/d@1"]}
    )
    assert set(found) == {"/run/sources/0", "/run/sources/1", "/run/sources"}

    assert set(violations({"runner": "integration"})) == {"/run/check", "/run/sources"}
    assert violations({"runner": "shell", "command": "true", "source": USERS}) == {
        "/run/source": "runner shell does not take source"
    }
    assert violations({"runner": "someday", "anything": "goes"}) == {}
