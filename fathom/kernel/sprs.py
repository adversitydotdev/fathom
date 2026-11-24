"""SPRS score, POA&M eligibility, and CMMC reminders for a Level 2 program.

Scoring follows 32 CFR 170.24 (CMMC Scoring Methodology; the DoD Assessment
Methodology v1.2.1 values): start at 110 and subtract the weight of every
NOT MET requirement. POA&M eligibility follows 32 CFR 170.21. The weights and
rules are data (`data/cmmc_l2_scoring.json`, source cited inside); this module
only applies them.

Mapping from computed status (RFC 0001 section 8): a requirement is MET only
when its coverage is `covered`. `contribution`, `gap`, `unmapped`, and a
requirement missing from the effective baseline are all NOT MET. That is the
conservative reading: a requirement is scored MET only when every unit of it
has a path whose source controls are all met.

Two inputs are not objects in RFC 0001 and are read from the program's
`extensions["dev.ogrl.cmmc"]` (the key the library baseline already uses):

- `assessment_date`, `conditional_status_date`, `last_affirmation_date`: ISO dates.
- `partial_credit`: practice IDs (`IA.L2-3.5.3`, `SC.L2-3.13.11`) an assessor
  attests are partially effective (MFA for remote and privileged users only;
  encryption employed but not FIPS-validated). It only changes the weight of a
  requirement that is already NOT MET.
"""

import json
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from fractions import Fraction
from functools import cache
from pathlib import Path
from typing import Any

from fathom.kernel import status
from fathom.kernel.baselines import effective
from fathom.kernel.graph import Graph
from fathom.kernel.models import Baseline, Program
from fathom.kernel.timeutil import utc

EXTENSION = "dev.ogrl.cmmc"
GV_13 = "control--ogrl-gv-13"
SSP_REQUIREMENT_PRACTICE = "CA.L2-3.12.4"
DUE_SOON_DAYS = 30  # the same horizon as the summary's expiring counts
REASSESSMENT_YEARS = 3
AFFIRMATION_YEARS = 1
DATA = Path(__file__).parent / "data" / "cmmc_l2_scoring.json"


@cache
def scoring() -> dict[str, Any]:
    return json.loads(DATA.read_text())


@dataclass
class Reason:
    code: str
    detail: str


@dataclass
class PoamItem:
    requirement_id: str
    practice_id: str
    state: str  # the requirement's coverage state, or `not-in-baseline`
    points: int  # what the requirement costs, with partial credit applied
    partial: bool
    eligible: bool
    reasons: list[Reason]
    due: date | None
    risk_ids: list[str]


@dataclass
class Conditional:
    status_date: date
    expires: date
    expired: bool
    days_remaining: int


@dataclass
class Poam:
    required: bool
    eligible: bool
    reasons: list[Reason]
    items: list[PoamItem]
    conditional: Conditional | None


@dataclass
class Reminder:
    kind: str  # `reassessment` or `affirmation`
    state: str  # `unscheduled`, `ok`, `due-soon`, or `overdue`
    due: date | None
    days_until: int | None
    last: date | None = None


@dataclass
class Reminders:
    reassessment: Reminder
    affirmation: Reminder
    affirming_official: str | None
    assessment_type: str | None
    assessment_cadence: str | None


@dataclass
class SprsReport:
    program_id: str
    at: datetime
    max_score: int
    score: int
    assessable: bool
    assessable_reason: str | None
    met: int
    not_met: int
    poam: Poam
    reminders: Reminders
    notes: list[str] = field(default_factory=list)


class NotCmmcLevel2(Exception):
    """The program's baseline is not CMMC Level 2."""


class InvalidInput(ValueError):
    """A `dev.ogrl.cmmc` program extension value is unusable."""


def add_years(day: date, years: int) -> date:
    try:
        return day.replace(year=day.year + years)
    except ValueError:  # 29 February
        return day.replace(year=day.year + years, day=28)


def _is_level_2(graph: Graph, baseline: Baseline | None) -> bool:
    layers = [baseline, graph.baseline(baseline.extends_ref) if baseline else None]
    return any(
        b is not None and (b.extensions or {}).get(EXTENSION, {}).get("level") == 2 for b in layers
    )


def _date(settings: dict[str, Any], key: str) -> date | None:
    value = settings.get(key)
    if value in (None, ""):
        return None
    try:
        return value if isinstance(value, date) else date.fromisoformat(str(value))
    except ValueError as exc:
        raise InvalidInput(f"{EXTENSION}.{key} is not an ISO date: {value!r}") from exc


def _partial(settings: dict[str, Any], requirements: dict[str, Any]) -> set[str]:
    by_practice = {v["practice_id"]: k for k, v in requirements.items()}
    result: set[str] = set()
    for practice in settings.get("partial_credit") or []:
        requirement_id = by_practice.get(practice)
        if requirement_id is None or "partial_points" not in requirements[requirement_id]:
            raise InvalidInput(
                f"{EXTENSION}.partial_credit: {practice!r} is not a practice with partial credit"
            )
        result.add(requirement_id)
    return result


def _reminder(kind: str, due: date | None, today: date, last: date | None = None) -> Reminder:
    if due is None:
        return Reminder(kind, "unscheduled", None, None, last)
    days = (due - today).days
    state = "overdue" if days < 0 else "due-soon" if days <= DUE_SOON_DAYS else "ok"
    return Reminder(kind, state, due, days, last)


def _gv13(graph: Graph, bindings: dict[str, dict[str, str]]) -> dict[str, str | None]:
    control = graph.control(GV_13)
    bound = bindings.get(GV_13, {})
    values: dict[str, str | None] = {}
    for name in ("affirming_official", "cmmc_assessment_type", "cmmc_assessment_frequency"):
        default = control.parameters.get(name) if control and control.parameters else None
        value = bound.get(name) or (default.value if default else None)
        values[name] = " ".join(value.split()) if value else None
    return values


def compute(graph: Graph, program: Program, at: datetime) -> SprsReport:
    at = utc(at)
    today = at.date()
    baseline = graph.baseline(program.baseline_ref)
    if baseline is None or not _is_level_2(graph, baseline):
        raise NotCmmcLevel2(f"program {program.id} is not on a CMMC Level 2 baseline")
    rules = scoring()
    weights: dict[str, dict[str, Any]] = rules["requirements"]
    settings = (program.extensions or {}).get(EXTENSION) or {}
    assessment_date = _date(settings, "assessment_date")
    conditional_date = _date(settings, "conditional_status_date")
    last_affirmation = _date(settings, "last_affirmation_date")
    partial = _partial(settings, weights)

    evaluation = status.evaluate(graph, program, at)
    coverage = {r.requirement_id: r for r in evaluation.requirements}
    in_baseline = set(effective(graph, baseline).requirement_ids)

    def state_of(requirement_id: str) -> str:
        if requirement_id not in in_baseline or requirement_id not in coverage:
            return "not-in-baseline"
        return coverage[requirement_id].state

    def cost(requirement_id: str) -> int:
        entry = weights[requirement_id]
        if requirement_id in partial:
            return int(entry["partial_points"])
        return int(entry.get("points", 0))

    never = set(rules["poam"]["never"])
    ssp_id = next(k for k, v in weights.items() if v["practice_id"] == SSP_REQUIREMENT_PRACTICE)
    assessable = state_of(ssp_id) == status.COVERED
    deadline = (
        conditional_date + timedelta(days=rules["poam"]["closeout_days"])
        if conditional_date
        else None
    )
    risks = [r for r in graph.risks() if r.status in ("open", "treating")]

    score = int(rules["max_score"])
    met = 0
    items: list[PoamItem] = []
    for requirement_id, entry in weights.items():
        state = state_of(requirement_id)
        if state == status.COVERED:
            met += 1
            continue
        points = cost(requirement_id)
        score -= points
        reasons: list[Reason] = []
        practice = entry["practice_id"]
        if requirement_id in never:
            reasons.append(Reason("never-on-poam", f"{practice} may never be on a POA&M"))
        if points > rules["poam"]["max_item_points"] and not (
            requirement_id == rules["poam"]["partial_exception"]
            and points == entry["partial_points"]
        ):
            reasons.append(
                Reason(
                    "points-exceed-limit",
                    f"{practice} is worth {points} points; a POA&M item may be worth at most "
                    f"{rules['poam']['max_item_points']}",
                )
            )
        controls = (
            set(coverage[requirement_id].unmet_control_ids) if state != "not-in-baseline" else set()
        )
        items.append(
            PoamItem(
                requirement_id=requirement_id,
                practice_id=practice,
                state=state,
                points=points,
                partial=requirement_id in partial,
                eligible=not reasons,
                reasons=reasons,
                due=deadline,
                risk_ids=sorted(r.id for r in risks if controls & set(r.control_refs or [])),
            )
        )

    # 3.12.4 carries no points, so a missing SSP is only visible through assessable.
    not_met = len(items)
    ratio = Fraction(score, rules["max_score"])
    reasons = []
    if not assessable:
        reasons.append(
            Reason(
                "no-ssp", f"{SSP_REQUIREMENT_PRACTICE} is not met: no assessment can be completed"
            )
        )
    if ratio < Fraction(str(rules["poam"]["conditional_min_ratio"])):
        reasons.append(
            Reason(
                "score-below-threshold",
                f"score {score}/{rules['max_score']} is below "
                f"{rules['poam']['conditional_min_ratio']:.0%} of the maximum",
            )
        )
    blocked = [i.practice_id for i in items if not i.eligible]
    if blocked:
        reasons.append(
            Reason(
                "ineligible-items",
                f"{len(blocked)} NOT MET requirements may not be on a POA&M (see items)",
            )
        )
    conditional = None
    if conditional_date:
        expires = deadline
        assert expires is not None
        conditional = Conditional(
            conditional_date, expires, today > expires, (expires - today).days
        )

    notes = []
    if conditional_date and reasons:
        notes.append("a conditional status date is set but the program is not POA&M eligible")
    if partial:
        notes.append(
            "partial credit is attested for: "
            + ", ".join(sorted(weights[r]["practice_id"] for r in partial))
        )
    if not assessable:
        notes.append(
            "the score is indicative: without an SSP (3.12.4) no assessment can be completed"
        )

    bindings = effective(graph, baseline).parameter_bindings
    gv13 = _gv13(graph, bindings)
    reassessment_due = add_years(assessment_date, REASSESSMENT_YEARS) if assessment_date else None
    if last_affirmation:
        affirmation_due: date | None = add_years(last_affirmation, AFFIRMATION_YEARS)
    else:
        affirmation_due = assessment_date  # an affirmation follows each assessment
    return SprsReport(
        program_id=program.id,
        at=at,
        max_score=rules["max_score"],
        score=score,
        assessable=assessable,
        assessable_reason=None if assessable else reasons[0].detail,
        met=met,
        not_met=not_met,
        poam=Poam(
            required=bool(items),
            eligible=not reasons,
            reasons=reasons,
            items=items,
            conditional=conditional,
        ),
        reminders=Reminders(
            reassessment=_reminder("reassessment", reassessment_due, today, assessment_date),
            affirmation=_reminder("affirmation", affirmation_due, today, last_affirmation),
            affirming_official=gv13["affirming_official"],
            assessment_type=gv13["cmmc_assessment_type"],
            assessment_cadence=gv13["cmmc_assessment_frequency"],
        ),
        notes=notes,
    )
