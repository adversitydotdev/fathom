"""Computed status (RFC 0001 section 8) through the API, and the kernel rules directly."""

from datetime import UTC, datetime, timedelta

from opengrc.kernel import status
from opengrc.kernel.graph import Graph
from opengrc.kernel.models import parse
from tests.conftest import AC2, AC3, C1, C2, LIB_BASELINE, LIB_TEST, STAMP, Api, library_objects

AC2_A = "mapping--ogrc-ac-01_to_nist-sp-800-53-r5-ac-2_part_a"
AC2_J = "mapping--ogrc-ac-02_to_nist-sp-800-53-r5-ac-2_part_j"


def states(api: Api, program_id: str, at: datetime | None = None):
    query = f"?at={at.isoformat().replace('+00:00', 'Z')}" if at else ""
    body = api.get(f"/programs/{program_id}/status{query}")
    return (
        {c["control_id"]: c for c in body["controls"]},
        {r["requirement_id"]: r for r in body["requirements"]},
    )


def fulfilling_test(api: Api, command: str = "echo ok > users.json; echo '3 users'") -> dict:
    return api.post("/tests", {
        "name": "IdP users unique", "control_ref": C1, "method": "automated",
        "fulfills_ref": LIB_TEST, "interval": "monthly",
        "run": {"runner": "shell", "command": command, "env": ["IDP_TENANT"],
                "evidence": [{"path": "users.json", "name": "IdP users",
                              "media_type": "application/json"}]},
    })


def test_a_program_moves_from_gap_to_met(pulled: Api, program):
    pid, sid = program["program"], program["system"]
    controls, reqs = states(pulled, pid)
    assert controls[C1]["state"] == "gap" and controls[C1]["failed"] == [
        "no implementation on the system or its components"
    ]
    assert reqs[AC2]["state"] == "contribution"  # part j has no full path
    assert reqs[AC3]["state"] == "unmapped"  # the only mapping is a draft

    impl = pulled.post("/implementations", {"system_ref": sid, "control_ref": C1,
                                            "status": "implemented", "responsibility": "provider"})
    before_any_run = datetime.now(UTC)
    controls, _ = states(pulled, pid)
    assert any("no methodology" in f for f in controls[C1]["failed"])

    test = fulfilling_test(pulled)
    controls, _ = states(pulled, pid)
    assert any("has no result" in f for f in controls[C1]["failed"])

    job = pulled.post(f"/tests/{test['id']}/runs", {"implementation_id": impl["id"]}, expect=202)
    assert job["status"] == "succeeded", job
    result = pulled.get(f"/results/{job['result_id']}")
    assert result["outcome"] == "pass" and result["summary"] == "3 users"
    evidence = pulled.get(f"/evidence/{result['evidence_refs'][0]}")
    assert evidence["method"] == "automated" and evidence["resource"]["digest"]["value"]

    controls, _ = states(pulled, pid)
    assert controls[C1]["state"] == "met", controls[C1]
    stale, _ = states(pulled, pid, datetime.now(UTC) + timedelta(days=40))
    assert stale[C1]["state"] == "gap"
    assert any("older than its monthly window" in f for f in stale[C1]["failed"])

    # Past status uses past objects: before the run, the control had no result.
    past, _ = states(pulled, pid, before_any_run)
    assert past[C1]["state"] == "gap"

    summary = pulled.get(f"/programs/{pid}/summary")
    assert summary["controls"] == {"met": 1, "gap": 1, "waived": 0, "out_of_scope": 0}
    gaps = pulled.get(f"/systems/{sid}/gaps")["gaps"]
    assert [g["control_id"] for g in gaps] == [C2]


def test_waived_and_out_of_scope(pulled: Api, program):
    pid, sid = program["program"], program["system"]
    impl = pulled.post("/implementations", {"system_ref": sid, "control_ref": C2,
                                            "status": "not-applicable",
                                            "responsibility": "provider", "narrative": "No IdP."})
    controls, _ = states(pulled, pid)
    assert controls[C2]["state"] == "out_of_scope"

    impl = pulled.patch(f"/implementations/{impl['id']}", {"status": "exception"}, impl["modified"])
    controls, _ = states(pulled, pid)
    assert controls[C2]["state"] == "gap"  # status exception needs an unexpired exception
    pulled.post("/exceptions", {"implementation_ref": impl["id"], "justification": "Cutover.",
                                "expires": "2099-01-01", "approver_ref": program["owner"]})
    controls, _ = states(pulled, pid)
    assert controls[C2]["state"] == "waived"
    later, _ = states(pulled, pid, datetime(2099, 1, 2, tzinfo=UTC))
    assert later[C2]["state"] == "gap"


def test_requirement_coverage_paths(pulled: Api, program):
    pid, sid = program["program"], program["system"]
    for control in (C1, C2):
        impl = pulled.post("/implementations", {"system_ref": sid, "control_ref": control,
                                                "status": "implemented",
                                                "responsibility": "provider"})
        pulled.post("/evidence", {"name": "Screenshot", "method": "link",
                                  "implementation_ref": impl["id"], "valid_until": "2099-01-01",
                                  "resource": {"uri": "https://wiki.example/x"}})
    # C1 still needs its library test carried out; give it a manual fulfilling test.
    manual = pulled.post("/tests", {"name": "Manual check", "control_ref": C1, "method": "manual",
                                    "fulfills_ref": LIB_TEST, "interval": "annual"})
    c1_impl = pulled.get(f"/implementations?control_id={C1}")["data"][0]
    pulled.post("/results", {"test_ref": manual["id"], "implementation_ref": c1_impl["id"],
                             "observed": datetime.now(UTC).isoformat(), "outcome": "pass"})
    controls, reqs = states(pulled, pid)
    assert controls[C1]["state"] == controls[C2]["state"] == "met"
    assert reqs[AC2]["state"] == "contribution"  # j: C2 is subset-of and still a draft

    # The organization re-authors the j mapping as a combined set with C1.
    with_c1 = pulled.post("/mappings", {"source_ref": C1, "target_ref": f"{AC2}#j",
                                        "relationship": "subset-of", "review_status": "reviewed"})
    pulled.post("/mappings", {"source_ref": C2, "target_ref": f"{AC2}#j",
                              "relationship": "subset-of", "review_status": "reviewed",
                              "combined_with_refs": [with_c1["id"]]})
    _, reqs = states(pulled, pid)
    assert reqs[AC2]["state"] == "covered", reqs[AC2]
    assert AC2_J not in reqs[AC2]["mapping_ids"]  # the library mapping is replaced

    # A current rejection of the library mapping on part a takes it out.
    pulled.post("/mapping-reviews", {"mapping_ref": AC2_A, "review_status": "rejected"})
    _, reqs = states(pulled, pid)
    assert reqs[AC2]["state"] == "contribution"


def test_status_is_404_for_unknown_program(pulled: Api):
    pulled.get("/programs/program--com.acme.nope/status", expect=404)


# --- kernel ---------------------------------------------------------------------------------


def graph_of(*extra: dict) -> Graph:
    library = [parse(o) for o in library_objects()]
    objects = [parse(o) for o in extra]
    provider_ids = [o.id for o in objects if getattr(o, "origin", None) == "provider"]
    return Graph([*library, *objects], [o.id for o in library], provider_ids)


ENV = {"spec_version": "0.1.0", "created": STAMP, "modified": STAMP}
SYSTEM = {"type": "system", "id": "system--com.acme.prod", **ENV, "name": "Prod",
          "component_refs": ["component--com.example.idp"]}
COMPONENT = {"type": "component", "id": "component--com.example.idp", **ENV, "name": "IdP",
             "kind": "service"}
PROGRAM = {"type": "program", "id": "program--com.acme.p", **ENV, "name": "P",
           "system_ref": SYSTEM["id"], "baseline_ref": LIB_BASELINE}
AT = datetime(2026, 11, 9, tzinfo=UTC)


def evaluate(*extra: dict):
    graph = graph_of(SYSTEM, COMPONENT, PROGRAM, *extra)
    return {c.control_id: c for c in status.evaluate(graph, graph.program(PROGRAM["id"]), AT).controls}


def test_provider_row_evidence_satisfies_an_unfulfilled_library_test():
    provider = {"type": "implementation", "id": "implementation--com.example.idp-ac-01", **ENV,
                "origin": "provider", "component_ref": COMPONENT["id"], "control_ref": C1,
                "status": "implemented", "responsibility": "provider"}
    assert "provider row" in evaluate(provider)[C1].failed[0]
    report = {"type": "evidence", "id": "evidence--com.example.soc2", **ENV, "name": "SOC 2",
              "method": "attestation", "implementation_ref": provider["id"],
              "valid_until": "2027-06-01",
              "resource": {"uri": "https://example.com/soc2.pdf",
                           "digest": {"algorithm": "sha-256", "value": "00"}}}
    assert evaluate(provider, report)[C1].state == "met"


def test_provider_shared_half_needs_the_organizations_half():
    half = {"type": "implementation", "id": "implementation--com.example.idp-ac-02", **ENV,
            "origin": "provider", "component_ref": COMPONENT["id"], "control_ref": C2,
            "status": "implemented", "responsibility": "shared",
            "customer_responsibility": "Review guests."}
    alone = evaluate(half)[C2]
    assert alone.state == "gap" and "organization's implementation is missing" in alone.failed[0]
    own = {"type": "implementation", "id": "implementation--com.acme.ac-02", **ENV,
           "system_ref": SYSTEM["id"], "control_ref": C2, "status": "implemented",
           "responsibility": "shared"}
    evidence = {"type": "evidence", "id": "evidence--com.acme.review", **ENV, "name": "Review",
                "method": "link", "implementation_ref": own["id"], "valid_until": "2027-01-01"}
    both = evaluate(half, own, evidence)[C2]
    assert both.state == "met" and both.implementation_ids == [own["id"]]
    expired = {**evidence, "id": "evidence--com.example.old", "implementation_ref": half["id"],
               "valid_until": "2026-01-01"}
    assert evaluate(half, own, evidence, expired)[C2].state == "gap"


def test_requirement_only_provider_row_joins_through_a_reviewed_mapping():
    row = {"type": "implementation", "id": "implementation--com.example.idp-ac-2", **ENV,
           "origin": "provider", "component_ref": COMPONENT["id"], "requirement_ref": AC2,
           "status": "implemented", "responsibility": "provider"}
    # C1 maps to AC-2#a, equal-to and reviewed: the row joins C1.
    assert evaluate(row)[C1].implementation_ids == [row["id"]]
    # C2's mapping to AC-3 is intersects-with: a row speaking AC-3 does not join.
    ac3 = {**row, "id": "implementation--com.example.idp-ac-3", "requirement_ref": AC3}
    assert evaluate(ac3)[C2].implementation_ids == []


def test_unresolved_parameter_is_a_gap():
    graph_objects = [o for o in library_objects()]
    for o in graph_objects:
        if o["id"] == C2:
            o["parameters"] = {"access_review_frequency": {"label": "how often"}}
            o["statement"] = "Accounts are reviewed {{ access_review_frequency }}."
    library = [parse(o) for o in graph_objects]
    own = parse({"type": "implementation", "id": "implementation--com.acme.ac-02", **ENV,
                 "system_ref": SYSTEM["id"], "control_ref": C2, "status": "implemented",
                 "responsibility": "provider"})
    evidence = parse({"type": "evidence", "id": "evidence--com.acme.e", **ENV, "name": "e",
                      "method": "link", "implementation_ref": own.id})
    extras = [parse(SYSTEM), parse(COMPONENT), parse(PROGRAM), own, evidence]
    graph = Graph([*library, *extras], [o.id for o in library])
    result = {c.control_id: c for c in status.evaluate(graph, graph.program(PROGRAM["id"]), AT).controls}
    assert "parameter access_review_frequency has no value" in result[C2].failed[0]
