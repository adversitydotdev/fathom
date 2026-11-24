"""SPRS score, POA&M eligibility, and reminders (32 CFR 170.24, 170.21) for CMMC Level 2.

The library here is a synthetic one: the 110 SP 800-171 Rev 2 requirements, one control
per requirement, one reviewed `equal-to` mapping each, and the `baseline--ogrl-cmmc-l2`
baseline. A requirement is made MET by an implemented implementation with unexpired
evidence, and NOT MET by leaving the control without one (a gap), so the kernel's real
section 8 computation decides every state.
"""

from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest

from fathom.kernel import sprs
from fathom.kernel.graph import Graph
from fathom.kernel.models import parse
from tests.conftest import STAMP, Api, write_library

ENV = {"spec_version": "0.1.0", "created": STAMP, "modified": STAMP}
FW = "framework--nist-sp-800-171-r2"
BASELINE = "baseline--ogrl-cmmc-l2"
SYSTEM = "system--com.acme.enclave"
PROGRAM = "program--com.acme.cmmc"
GV13 = "control--ogrl-gv-13"
AT = datetime(2026, 11, 24, 12, tzinfo=UTC)

RULES = sprs.scoring()
REQS: dict[str, dict[str, Any]] = RULES["requirements"]
BY_PRACTICE = {v["practice_id"]: k for k, v in REQS.items()}


def req(number: str) -> str:
    """`3.1.1` -> the requirement id."""
    return f"requirement--nist-sp-800-171-r2-{number.replace('.', '-')}"


def control_of(requirement_id: str) -> str:
    return "control--ogrl-t-" + requirement_id.split("r2-")[1]


def library(*, bindings: dict[str, dict[str, str]] | None = None) -> list[dict[str, Any]]:
    objects: list[dict[str, Any]] = [
        {
            "type": "framework",
            "id": FW,
            **ENV,
            "name": "NIST SP 800-171 Revision 2",
            "publisher": "NIST",
            "version": "2",
            "reproduction": "permitted",
        }
    ]
    for rid in REQS:
        number = rid.split("r2-")[1].replace("-", ".")
        objects.append(
            {
                "type": "requirement",
                "id": rid,
                **ENV,
                "display_id": number,
                "name": f"Requirement {number}",
                "framework_ref": FW,
                "class": "control",
            }
        )
        cid = control_of(rid)
        objects.append(
            {
                "type": "control",
                "id": cid,
                **ENV,
                "display_id": cid.split("ogrl-")[1].upper(),
                "name": f"Control {number}",
                "origin": "standard",
                "family": "ac",
                "statement": "Do the thing.",
                "objective": "The thing is done.",
            }
        )
        objects.append(
            {
                "type": "mapping",
                "id": f"mapping--{cid.split('--')[1]}_to_{rid.split('--')[1]}",
                **ENV,
                "source_ref": cid,
                "target_ref": rid,
                "relationship": "equal-to",
                "rationale": "functional",
                "review_status": "reviewed",
            }
        )
    objects.append(
        {
            "type": "control",
            "id": GV13,
            **ENV,
            "display_id": "OGRL-GV-13",
            "name": "CMMC assessment and affirmation",
            "origin": "standard",
            "family": "gv",
            "statement": "Affirm via {{ affirming_official }}.",
            "objective": "Affirmed.",
            "parameters": {
                "affirming_official": {"label": "official", "value": "the Affirming Official"},
                "cmmc_assessment_type": {"label": "type", "value": "Level 2 self-assessment"},
                "cmmc_assessment_frequency": {"label": "cadence", "value": "every three years"},
            },
        }
    )
    objects.append(
        {
            "type": "baseline",
            "id": BASELINE,
            **ENV,
            "name": "CMMC Level 2",
            "framework_refs": [FW],
            "control_refs": [control_of(r) for r in REQS],
            "requirement_refs": list(REQS),
            "parameter_bindings": bindings or {},
            "extensions": {"dev.ogrl.cmmc": {"level": 2}},
        }
    )
    return objects


def organization(
    not_met: set[str], settings: dict[str, Any] | None = None, risks: list[dict] | None = None
) -> list[dict[str, Any]]:
    """Every requirement MET except those in `not_met` (NIST numbers such as `3.1.1`)."""
    unmet = {req(n) for n in not_met}
    objects: list[dict[str, Any]] = [
        {"type": "system", "id": SYSTEM, **ENV, "name": "Enclave"},
        {
            "type": "program",
            "id": PROGRAM,
            **ENV,
            "name": "CMMC L2",
            "system_ref": SYSTEM,
            "baseline_ref": BASELINE,
            **({"extensions": {"dev.ogrl.cmmc": settings}} if settings else {}),
        },
    ]
    for rid in REQS:
        if rid in unmet:
            continue
        slug = rid.split("r2-")[1]
        impl = f"implementation--com.acme.t-{slug}"
        objects.append(
            {
                "type": "implementation",
                "id": impl,
                **ENV,
                "system_ref": SYSTEM,
                "control_ref": control_of(rid),
                "status": "implemented",
                "responsibility": "provider",
            }
        )
        objects.append(
            {
                "type": "evidence",
                "id": f"evidence--com.acme.t-{slug}",
                **ENV,
                "name": "proof",
                "method": "link",
                "implementation_ref": impl,
                "valid_until": "2027-12-31",
            }
        )
    return [*objects, *(risks or [])]


def compute(
    not_met: set[str],
    settings: dict[str, Any] | None = None,
    at: datetime = AT,
    risks: list[dict] | None = None,
    bindings: dict[str, dict[str, str]] | None = None,
) -> sprs.SprsReport:
    lib = [parse(o) for o in library(bindings=bindings)]
    org = [parse(o) for o in organization(not_met, settings, risks)]
    graph = Graph([*lib, *org], [o.id for o in lib])
    program = graph.program(PROGRAM)
    assert program is not None
    return sprs.compute(graph, program, at)


def codes(reasons: list[sprs.Reason]) -> set[str]:
    return {r.code for r in reasons}


def one_pointers(count: int) -> set[str]:
    """`count` requirements worth 1 point that may be on a POA&M."""
    never = set(RULES["poam"]["never"])
    numbers = [
        rid.split("r2-")[1].replace("-", ".")
        for rid, v in REQS.items()
        if v.get("points") == 1 and rid not in never
    ]
    assert len(numbers) >= count
    return set(sorted(numbers)[:count])


# --- the data file ---------------------------------------------------------------------------


def test_weights_data_matches_the_published_totals():
    """32 CFR 170.24 lists 42 five-point and 14 three-point requirements; every other derived
    requirement is one point; 3.5.3 and 3.13.11 are five-point with partial credit (44
    five-pointers in all); 3.12.4 is unscored. Deductions total 44*5 + 14*3 + 51 = 313, so the
    scale runs from 110 down to -203.
    """
    points = [v.get("points", 0) for v in REQS.values()]
    assert len(REQS) == 110
    assert sum(points) == 313
    assert RULES["max_score"] - sum(points) == -203
    assert sum(1 for p in points if p == 5) == 44
    assert sum(1 for p in points if p == 3) == 14
    assert sum(1 for p in points if p == 1) == 51
    assert sorted({p for p in points}) == [0, 1, 3, 5]
    assert [k for k, v in REQS.items() if v.get("ssp_required")] == [req("3.12.4")]
    assert {k for k, v in REQS.items() if "partial_points" in v} == {req("3.5.3"), req("3.13.11")}


def test_library_baseline_extension_agrees_when_the_library_is_checked_out():
    """The ogrl-library CMMC L2 baseline carries its own points; they must equal ours."""
    path = Path(__file__).parents[2] / "ogrl-library/library/baseline/ogrl-cmmc-l2.yaml"
    if not path.exists():
        pytest.skip("ogrl-library is not checked out beside this repository")
    import yaml

    theirs = yaml.safe_load(path.read_text())["extensions"]["dev.ogrl.cmmc"]["requirements"]
    assert set(theirs) == set(REQS)
    for rid, entry in REQS.items():
        assert theirs[rid]["practice_id"] == entry["practice_id"]
        assert theirs[rid].get("points") == entry.get("points")
        assert theirs[rid].get("partial_points") == entry.get("partial_points")


# --- scoring ---------------------------------------------------------------------------------


def test_hand_worked_example():
    """Six requirements NOT MET; the other 104 are MET.

    Weights (32 CFR 170.24):
      3.1.1   AC.L2-3.1.1    basic, 5 points
      3.14.1  SI.L2-3.14.1   basic, 5 points
      3.3.2   AU.L2-3.3.2    basic, 3 points
      3.1.3   AC.L2-3.1.3    derived, 1 point
      3.13.11 SC.L2-3.13.11  no encryption attested, 5 points
      3.5.3   IA.L2-3.5.3    MFA for remote and privileged users only: partial, 3 points
    Deductions: 5 + 5 + 3 + 1 + 5 + 3 = 22.
    Score: 110 - 22 = 88, and 88 / 110 = 0.8 exactly, so the 80% test passes.
    POA&M: 3.1.1, 3.14.1 (5 points), 3.3.2 (3 points), 3.13.11 (5 points: encryption is not
    employed, so the 3-point exception does not apply) and 3.5.3 (partial, still 3 points)
    exceed the 1-point limit. Only 3.1.3 is eligible, so the program is not eligible.
    """
    report = compute(
        {"3.1.1", "3.14.1", "3.3.2", "3.1.3", "3.13.11", "3.5.3"},
        {"partial_credit": ["IA.L2-3.5.3"]},
    )
    assert report.score == 88
    assert (report.met, report.not_met) == (104, 6)
    assert report.assessable
    assert {i.practice_id: i.points for i in report.poam.items} == {
        "AC.L2-3.1.1": 5,
        "SI.L2-3.14.1": 5,
        "AU.L2-3.3.2": 3,
        "AC.L2-3.1.3": 1,
        "SC.L2-3.13.11": 5,
        "IA.L2-3.5.3": 3,
    }
    assert {i.practice_id for i in report.poam.items if i.eligible} == {"AC.L2-3.1.3"}
    assert report.poam.required and not report.poam.eligible
    assert codes(report.poam.reasons) == {"ineligible-items"}  # 88 / 110 is not below 0.8


def test_everything_met_scores_110_and_needs_no_poam():
    report = compute(set())
    assert (report.score, report.met, report.not_met) == (110, 110, 0)
    assert report.assessable and report.poam.eligible and not report.poam.required
    assert report.poam.items == []


def test_everything_not_met_is_the_scale_floor():
    report = compute({n.split("r2-")[1].replace("-", ".") for n in REQS})
    assert report.score == -203 and not report.assessable


def test_contribution_and_unmapped_are_not_met():
    """Only `covered` is MET. Dropping the mapping for 3.1.1 leaves it `unmapped`."""
    lib = [
        parse(o)
        for o in library()
        if o["id"] != "mapping--ogrl-t-3-1-1_to_nist-sp-800-171-r2-3-1-1"
    ]
    org = [parse(o) for o in organization(set())]
    graph = Graph([*lib, *org], [o.id for o in lib])
    program = graph.program(PROGRAM)
    assert program is not None
    report = sprs.compute(graph, program, AT)
    assert report.score == 105
    [item] = report.poam.items
    assert (item.practice_id, item.state) == ("AC.L2-3.1.1", "unmapped")


def test_3_13_11_partial_credit_costs_three_and_may_be_on_a_poam():
    """Encryption employed but not FIPS-validated: -3, and the one 3-point POA&M item."""
    attested = compute({"3.13.11"}, {"partial_credit": ["SC.L2-3.13.11"]})
    assert attested.score == 107
    [item] = attested.poam.items
    assert (item.points, item.partial, item.eligible, item.reasons) == (3, True, True, [])
    assert attested.poam.eligible

    none = compute({"3.13.11"})  # no encryption at all
    assert none.score == 105
    [item] = none.poam.items
    assert item.points == 5 and not item.eligible
    assert codes(item.reasons) == {"points-exceed-limit"}
    assert not none.poam.eligible


def test_3_5_3_partial_credit_costs_three_and_is_never_poam_eligible():
    attested = compute({"3.5.3"}, {"partial_credit": ["IA.L2-3.5.3"]})
    assert attested.score == 107
    [item] = attested.poam.items
    assert (item.points, item.eligible) == (3, False)
    assert codes(item.reasons) == {"points-exceed-limit"}
    assert compute({"3.5.3"}).score == 105


def test_partial_credit_does_not_change_a_requirement_that_is_met():
    assert compute(set(), {"partial_credit": ["IA.L2-3.5.3"]}).score == 110


def test_partial_credit_rejects_practices_without_it():
    with pytest.raises(sprs.InvalidInput):
        compute({"3.1.1"}, {"partial_credit": ["AC.L2-3.1.1"]})
    with pytest.raises(sprs.InvalidInput):
        compute(set(), {"assessment_date": "last tuesday"})


def test_missing_ssp_means_no_assessment():
    """3.12.4 carries no points: the score does not move, but nothing is assessable."""
    report = compute({"3.12.4"})
    assert report.score == 110 and not report.assessable
    assert "no-ssp" in codes(report.poam.reasons) and not report.poam.eligible
    assert "3.12.4" in (report.assessable_reason or "")
    [item] = report.poam.items
    assert (item.practice_id, item.points, item.eligible) == ("CA.L2-3.12.4", 0, False)


# --- POA&M eligibility -----------------------------------------------------------------------


@pytest.mark.parametrize(
    "number, practice",
    [
        ("3.1.20", "AC.L2-3.1.20"),
        ("3.1.22", "AC.L2-3.1.22"),
        ("3.10.3", "PE.L2-3.10.3"),
        ("3.10.4", "PE.L2-3.10.4"),
        ("3.10.5", "PE.L2-3.10.5"),
    ],
)
def test_requirements_that_may_never_be_on_a_poam(number: str, practice: str):
    """One point each, so the point rule alone would allow them; the exclusion list does not."""
    report = compute({number})
    assert report.score == 109
    [item] = report.poam.items
    assert item.practice_id == practice and item.points == 1 and not item.eligible
    assert codes(item.reasons) == {"never-on-poam"}
    assert not report.poam.eligible and "ineligible-items" in codes(report.poam.reasons)


def test_eighty_percent_boundary():
    """88 of 110 is exactly 0.8 and passes; 87 does not."""
    at_line = compute(one_pointers(22))
    assert at_line.score == 88 and at_line.poam.eligible and at_line.poam.reasons == []
    assert all(i.eligible for i in at_line.poam.items)

    below = compute(one_pointers(23))
    assert below.score == 87 and not below.poam.eligible
    assert codes(below.poam.reasons) == {"score-below-threshold"}


def test_poam_items_link_open_risks_on_unmet_controls():
    risk = {
        "type": "risk",
        "id": "risk--com.acme.session",
        **ENV,
        "name": "Sessions never lock",
        "statement": "x",
        "likelihood": 3,
        "impact": 2,
        "treatment": "mitigate",
        "status": "open",
        "control_refs": [control_of(req("3.1.10"))],
        "milestones": [{"name": "Lock", "due": "2027-01-01"}],
    }
    closed = {**risk, "id": "risk--com.acme.old", "status": "closed"}
    report = compute({"3.1.10"}, risks=[risk, closed])
    [item] = report.poam.items
    assert item.risk_ids == ["risk--com.acme.session"]


# --- the 180-day closeout --------------------------------------------------------------------


def test_conditional_status_expires_180_days_after_its_date():
    """2026-06-01 + 180 days = 2026-11-28. The last day counts; the next day is expired."""
    settings = {"conditional_status_date": "2026-06-01"}
    unmet = one_pointers(3)

    on_the_24th = compute(unmet, settings, datetime(2026, 11, 24, 9, tzinfo=UTC))
    conditional = on_the_24th.poam.conditional
    assert conditional is not None
    assert conditional.expires == date(2026, 11, 28)
    assert (conditional.expired, conditional.days_remaining) == (False, 4)
    assert {i.due for i in on_the_24th.poam.items} == {date(2026, 11, 28)}

    last_day = compute(unmet, settings, datetime(2026, 11, 28, 23, 59, tzinfo=UTC))
    assert last_day.poam.conditional and not last_day.poam.conditional.expired

    after = compute(unmet, settings, datetime(2026, 11, 29, 0, 1, tzinfo=UTC))
    assert after.poam.conditional and after.poam.conditional.expired
    assert after.poam.conditional.days_remaining == -1


def test_no_conditional_date_means_no_expiry_or_due_dates():
    report = compute(one_pointers(2))
    assert report.poam.conditional is None
    assert {i.due for i in report.poam.items} == {None}


def test_conditional_date_on_an_ineligible_program_is_flagged():
    report = compute({"3.1.1"}, {"conditional_status_date": "2026-10-01"})
    assert not report.poam.eligible and report.poam.conditional is not None
    assert any("not POA&M eligible" in n for n in report.notes)


# --- reminders -------------------------------------------------------------------------------


def test_reminders_from_the_assessment_and_affirmation_dates():
    settings = {"assessment_date": "2025-12-01", "last_affirmation_date": "2026-01-15"}
    reminders = compute(set(), settings).reminders
    assert reminders.reassessment.due == date(2028, 12, 1)
    assert reminders.reassessment.state == "ok"
    assert reminders.affirmation.due == date(2027, 1, 15)
    assert (reminders.affirmation.days_until, reminders.affirmation.state) == (52, "ok")

    soon = compute(set(), settings, datetime(2026, 12, 20, tzinfo=UTC)).reminders
    assert (soon.affirmation.days_until, soon.affirmation.state) == (26, "due-soon")
    late = compute(set(), settings, datetime(2027, 1, 16, tzinfo=UTC)).reminders
    assert (late.affirmation.days_until, late.affirmation.state) == (-1, "overdue")
    on_the_day = compute(set(), settings, datetime(2027, 1, 15, 23, tzinfo=UTC)).reminders
    assert on_the_day.affirmation.state == "due-soon"


def test_first_affirmation_falls_due_with_the_assessment():
    reminders = compute(set(), {"assessment_date": "2026-11-01"}).reminders
    assert reminders.affirmation.due == date(2026, 11, 1)
    assert reminders.affirmation.state == "overdue"
    assert reminders.reassessment.due == date(2029, 11, 1)


def test_three_year_reassessment_from_a_leap_day():
    reminders = compute(set(), {"assessment_date": "2024-02-29"}).reminders
    assert reminders.reassessment.due == date(2027, 2, 28)


def test_no_dates_means_unscheduled():
    reminders = compute(set()).reminders
    assert reminders.reassessment.state == "unscheduled" and reminders.reassessment.due is None
    assert reminders.affirmation.state == "unscheduled"


def test_gv_13_parameters_come_from_the_baseline_bindings_then_the_control():
    default = compute(set()).reminders
    assert default.affirming_official == "the Affirming Official"
    assert default.assessment_type == "Level 2 self-assessment"
    assert default.assessment_cadence == "every three years"

    bound = compute(
        set(),
        bindings={GV13: {"affirming_official": "the CEO", "cmmc_assessment_type": "C3PAO"}},
    ).reminders
    assert (bound.affirming_official, bound.assessment_type) == ("the CEO", "C3PAO")
    assert bound.assessment_cadence == "every three years"


# --- scope -----------------------------------------------------------------------------------


def test_a_program_off_cmmc_level_2_has_no_sprs():
    lib = [parse(o) for o in library()]
    for o in lib:
        if o.id == BASELINE:
            o.__dict__["extensions"] = None
    org = [parse(o) for o in organization(set())]
    graph = Graph([*lib, *org], [o.id for o in lib])
    program = graph.program(PROGRAM)
    assert program is not None
    with pytest.raises(sprs.NotCmmcLevel2):
        sprs.compute(graph, program, AT)


# --- the API ---------------------------------------------------------------------------------


@pytest.fixture
def library_dir(tmp_path: Path) -> Path:
    return write_library(tmp_path / "library", library())


def test_the_api_serves_the_report(pulled: Api):
    system = pulled.post("/systems", {"name": "Enclave"})
    program = pulled.post(
        "/programs",
        {
            "name": "CMMC L2",
            "system_ref": system["id"],
            "baseline_ref": BASELINE,
            "extensions": {
                "dev.ogrl.cmmc": {
                    "conditional_status_date": "2026-09-01",
                    "assessment_date": "2026-09-01",
                }
            },
        },
    )
    body = pulled.get(f"/programs/{program['id']}/sprs?at=2027-01-10T00:00:00Z")
    assert body["max_score"] == 110 and body["not_met"] == 110 and body["met"] == 0
    assert body["score"] == -203 and body["assessable"] is False
    assert body["poam"]["eligible"] is False and body["poam"]["conditional"]["expires"] == (
        "2027-02-28"
    )
    assert body["reminders"]["reassessment"]["due"] == "2029-09-01"
    first = body["poam"]["items"][0]
    assert {"requirement_id", "practice_id", "points", "eligible", "reasons", "due"} <= set(first)

    off = pulled.post(
        "/programs",
        {"name": "Other", "system_ref": system["id"], "baseline_ref": BASELINE},
    )
    pulled.get(f"/programs/{off['id']}/sprs")  # still CMMC: served without settings
    pulled.get("/programs/program--nope/sprs", expect=404)


def test_the_api_refuses_unusable_settings(pulled: Api):
    system = pulled.post("/systems", {"name": "Enclave"})
    program = pulled.post(
        "/programs",
        {
            "name": "CMMC L2",
            "system_ref": system["id"],
            "baseline_ref": BASELINE,
            "extensions": {"dev.ogrl.cmmc": {"assessment_date": "soon"}},
        },
    )
    pulled.get(f"/programs/{program['id']}/sprs", expect=400)
