"""The rules every collection shares (RFC 0004 section 3), and the per-type ones."""

import io

from tests.conftest import AC2, C1, C2, LIB_BASELINE, LIB_TEST, Api


def test_every_spec_operation_is_served():
    import yaml
    from pathlib import Path

    from opengrc.api.paths import all_endpoints

    spec = yaml.safe_load((Path(__file__).parents[1] / "api" / "openapi.yaml").read_text())
    operations = {
        op["operationId"]
        for item in spec["paths"].values()
        for op in item.values()
        if isinstance(op, dict) and "operationId" in op
    }
    assert operations == {e.id for e in all_endpoints()}


def test_library_objects_are_listed_and_read_only(pulled: Api):
    frameworks = pulled.get("/frameworks")["data"]
    assert [f["id"] for f in frameworks] == ["framework--nist-sp-800-53-r5"]
    requirement = pulled.get(f"/requirements/{AC2}")
    assert requirement["class"] == "control" and requirement["parts"][0]["id"] == "a"
    control = pulled.get(f"/controls/{C1}")
    problem = pulled.patch(f"/controls/{C1}", {"family": "zz"}, control["modified"], expect=409)
    assert problem["type"] == "urn:opengrc:problem:library-object"
    assert pulled.get(f"/requirements/{AC2}/mappings")["data"]
    assert [t["id"] for t in pulled.get(f"/controls/{C1}/tests")["data"]] == [LIB_TEST]


def test_unknown_fields_round_trip_and_merge_patch(admin: Api):
    party = admin.post("/parties", {"name": "Ops", "kind": "team", "x_custom": {"a": 1},
                                    "extensions": {"com.acme": {"k": "v"}}})
    assert party["x_custom"] == {"a": 1}
    assert party["extensions"] == {"com.acme": {"k": "v"}}
    assert party["created_by_ref"] == "party--administrator"
    assert "revoked" not in party  # absent means false; null is invalid in the language

    patched = admin.patch(f"/parties/{party['id']}", {"x_custom": None, "tags": ["a"]},
                          party["modified"])
    assert "x_custom" not in patched and patched["tags"] == ["a"]
    assert patched["modified"] > party["modified"]
    assert patched["extensions"] == {"com.acme": {"k": "v"}}


def test_ids_are_checked(admin: Api):
    taken = admin.post("/parties", {"id": "party--com.acme.ops", "name": "Ops", "kind": "team"})
    assert taken["id"] == "party--com.acme.ops"
    dup = admin.post("/parties", {"id": "party--com.acme.ops", "name": "x", "kind": "team"},
                     expect=409)
    assert dup["type"] == "urn:opengrc:problem:id-taken"
    wrong = admin.post("/parties", {"id": "system--com.acme.x", "name": "x", "kind": "team"},
                       expect=400)
    assert wrong["errors"][0]["pointer"] == "/id"
    reserved = admin.post("/parties", {"id": "party--ops", "name": "x", "kind": "team"}, expect=400)
    assert reserved["errors"][0]["pointer"] == "/id"
    bad = admin.post("/parties", {"name": "x", "kind": "robot"}, expect=400)
    assert bad["errors"][0]["pointer"] == "/kind"


def test_revoked_objects_are_hidden_and_ids_never_reused(admin: Api):
    party = admin.post("/parties", {"id": "party--com.acme.gone", "name": "Gone", "kind": "team"})
    admin.revoke(f"/parties/{party['id']}", party["modified"])
    assert all(p["id"] != party["id"] for p in admin.get("/parties")["data"])
    assert any(p["id"] == party["id"] for p in admin.get("/parties?revoked=true")["data"])
    admin.post("/parties", {"id": "party--com.acme.gone", "name": "Again", "kind": "team"},
               expect=409)


def test_pages_use_cursors(admin: Api):
    for i in range(5):
        admin.post("/parties", {"name": f"P{i}", "kind": "person"})
    first = admin.get("/parties?limit=2")
    assert len(first["data"]) == 2 and first["page"]["next_cursor"]
    seen = [p["id"] for p in first["data"]]
    cursor = first["page"]["next_cursor"]
    while cursor:
        page = admin.get(f"/parties?limit=2&cursor={cursor}")
        seen += [p["id"] for p in page["data"]]
        cursor = page["page"].get("next_cursor")
    assert len(seen) == 5 == len(set(seen))
    admin.get("/parties?limit=500", expect=400)


def test_graph_constraints_are_400_with_pointers(pulled: Api, program):
    problem = pulled.post("/implementations", {"system_ref": "system--com.acme.nope",
                                               "control_ref": C1, "status": "planned",
                                               "responsibility": "provider"}, expect=400)
    assert problem["errors"][0]["pointer"] == "/system_ref"
    problem = pulled.post("/programs", {"name": "x", "system_ref": program["system"],
                                        "baseline_ref": C1}, expect=400)
    assert problem["errors"][0]["pointer"] == "/baseline_ref"


def test_one_implementation_per_system_and_control(pulled: Api, program):
    body = {"system_ref": program["system"], "control_ref": C1, "status": "planned",
            "responsibility": "provider"}
    pulled.post("/implementations", body)
    assert pulled.post("/implementations", body, expect=409)["type"].endswith("duplicate")
    origin = pulled.post("/implementations", {**body, "control_ref": C2, "origin": "provider"},
                         expect=400)
    assert origin["errors"][0]["pointer"] == "/origin"


def test_agent_drafts_and_a_person_attests(client, pulled: Api, program):
    agent = Api(client, "agent")
    body = {"system_ref": program["system"], "control_ref": C1, "status": "implemented",
            "responsibility": "provider", "narrative": "Drafted."}
    refused = agent.post("/implementations", body, expect=403)
    assert refused["type"] == "urn:opengrc:problem:agent-refused"
    draft = agent.post("/implementations", {**body, "status": "planned"})
    assert draft["created_by_ref"] == "party--agent"
    agent.revoke(f"/implementations/{draft['id']}", draft["modified"], expect=403)
    accepted = pulled.patch(f"/implementations/{draft['id']}", {"status": "implemented"},
                            draft["modified"])
    assert accepted["status"] == "implemented" and accepted["created_by_ref"] == "party--agent"
    # The gates are about the actor, not the role: an agent holding admin is still refused.
    rogue = Api(client, "rogue-agent")
    rogue.patch(f"/implementations/{draft['id']}", {"narrative": "x"}, accepted["modified"],
                expect=403)


def test_agent_gates_on_other_types(client, pulled: Api, program):
    agent = Api(client, "agent")
    rogue = Api(client, "rogue-agent")
    run = {"runner": "shell", "command": "true"}
    agent.post("/tests", {"name": "t", "control_ref": C1, "method": "automated", "run": run},
               expect=403)
    rogue.post("/mappings", {"source_ref": C1, "target_ref": AC2, "relationship": "subset-of",
                             "review_status": "reviewed"}, expect=403)
    rogue.post("/findings", {"name": "f", "system_ref": program["system"],
                             "objective_ref": f"{AC2}#obj.a", "determination": "satisfied",
                             "observed": "2026-11-01", "narrative": "n"}, expect=403)
    agent.post("/risks", {"name": "r", "statement": "s", "likelihood": 2, "impact": 3,
                          "treatment": "accept", "status": "accepted",
                          "approver_ref": program["owner"], "review_on": "2027-01-01"},
               expect=403)


def test_permissions_beyond_the_type(contributor: Api, pulled: Api, program):
    pulled.post("/mappings", {"source_ref": C1, "target_ref": AC2, "relationship": "subset-of",
                              "review_status": "draft"})
    contributor.post("/mappings", {"source_ref": C2, "target_ref": AC2,
                                   "relationship": "subset-of", "review_status": "reviewed"},
                     expect=403)
    contributor.post("/exceptions", {}, expect=403)
    contributor.post("/library/pull", {"version": "0.1.0"}, expect=403)


def test_one_organization_mapping_per_pair(pulled: Api):
    body = {"source_ref": C1, "target_ref": f"{AC2}#j", "relationship": "subset-of"}
    pulled.post("/mappings", body)
    pulled.post("/mappings", body, expect=409)
    bad = pulled.post("/mappings", {**body, "target_ref": f"{AC2}#zz"}, expect=400)
    assert bad["errors"][0]["pointer"] == "/target_ref"
    bad = pulled.post("/mappings", {**body, "target_ref": AC2,
                                    "parameter_map": {"ac_02_odp_10": "nope"}}, expect=400)
    assert bad["errors"][0]["pointer"] == "/parameter_map/ac_02_odp_10"


def test_tests_check_their_run_block(pulled: Api):
    base = {"name": "t", "control_ref": C1, "method": "automated"}
    pulled.post("/tests", {**base, "method": "manual", "run": {"runner": "shell", "command": "x"}},
                expect=400)
    bad = pulled.post("/tests", {**base, "run": {"runner": "shell", "command": "x",
                                                 "evidence": [{"path": "../x", "name": "x",
                                                               "media_type": "text/plain"}]}},
                      expect=400)
    assert bad["errors"][0]["pointer"] == "/run/evidence/0/path"
    pulled.post("/tests", {**base, "run": {"runner": "shell", "command": "x", "timeout": "61m"}},
                expect=400)
    pulled.post("/tests", {**base, "fulfills_ref": LIB_TEST,
                           "run": {"runner": "shell", "command": "exit 0"}})


def test_results_are_manual_and_immutable(pulled: Api, program):
    impl = pulled.post("/implementations", {"system_ref": program["system"], "control_ref": C1,
                                            "status": "planned", "responsibility": "provider"})
    manual = pulled.post("/tests", {"name": "Review", "control_ref": C1, "method": "manual"})
    body = {"test_ref": LIB_TEST, "implementation_ref": impl["id"],
            "observed": "2026-11-01T00:00:00Z", "outcome": "pass"}
    pulled.post("/results", body, expect=400)  # automated: the harness records it
    result = pulled.post("/results", {**body, "test_ref": manual["id"]})
    assert result["outcome"] == "pass"
    response = pulled.client.patch(f"/v1/results/{result['id']}", json={},
                                   headers=pulled.headers)
    assert response.status_code == 405


def test_evidence_freezes_once_complete(pulled: Api, program):
    impl = pulled.post("/implementations", {"system_ref": program["system"], "control_ref": C1,
                                            "status": "planned", "responsibility": "provider"})
    evidence = pulled.post("/evidence", {"name": "Export", "method": "upload",
                                         "implementation_ref": impl["id"],
                                         "valid_until": "2027-01-01"})
    evidence = pulled.patch(f"/evidence/{evidence['id']}", {"valid_until": "2027-02-01"},
                            evidence["modified"])
    uploaded = pulled.client.post(
        f"/v1/evidence/{evidence['id']}/content",
        headers={**pulled.headers, "If-Match": evidence["modified"]},
        files={"file": ("users.csv", io.BytesIO(b"a,b\n"), "text/csv")},
    )
    assert uploaded.status_code == 200, uploaded.text
    complete = uploaded.json()
    assert complete["resource"]["digest"]["algorithm"] == "sha-256"
    content = pulled.client.get(f"/v1/evidence/{evidence['id']}/content", headers=pulled.headers)
    assert content.content == b"a,b\n" and content.headers["content-type"].startswith("text/csv")
    frozen = pulled.patch(f"/evidence/{evidence['id']}", {"valid_until": "2028-01-01"},
                          complete["modified"], expect=409)
    assert frozen["type"].endswith("evidence-complete")
    renamed = pulled.patch(f"/evidence/{evidence['id']}", {"name": "Renamed"}, complete["modified"])
    assert renamed["name"] == "Renamed"


def test_policy_adoption_needs_content(pulled: Api, program):
    policy = pulled.post("/policies", {"name": "Access", "status": "draft",
                                       "owner_ref": program["owner"], "adopted": "2026-11-01",
                                       "resource": {"uri": "x", "digest": {"algorithm": "sha-256",
                                                                           "value": "0"}}})
    assert "resource" not in policy  # the body cannot set it; the content route does
    pulled.patch(f"/policies/{policy['id']}", {"status": "adopted"}, policy["modified"],
                 expect=400)
    bad = pulled.client.post(f"/v1/policies/{policy['id']}/content",
                             headers={**pulled.headers, "If-Match": policy["modified"]},
                             files={"file": ("p.exe", io.BytesIO(b"MZ"), "application/x-msdownload")})
    assert bad.status_code == 415
    ok = pulled.client.post(f"/v1/policies/{policy['id']}/content",
                            headers={**pulled.headers, "If-Match": policy["modified"]},
                            files={"file": ("p.md", io.BytesIO(b"# Access"), "text/markdown")})
    assert ok.status_code == 200, ok.text
    adopted = pulled.patch(f"/policies/{policy['id']}", {"status": "adopted"}, ok.json()["modified"])
    assert adopted["status"] == "adopted" and adopted["resource"]["media_type"] == "text/markdown"


def test_risk_acceptance_rules(pulled: Api, program):
    body = {"name": "Shared admin", "statement": "s", "likelihood": 2, "impact": 5,
            "treatment": "accept", "status": "accepted"}
    problem = pulled.post("/risks", body, expect=400)
    assert {e["pointer"] for e in problem["errors"]} == {"/approver_ref", "/review_on"}
    pulled.post("/risks", {**body, "likelihood": 6}, expect=400)
    risk = pulled.post("/risks", {**body, "approver_ref": program["owner"],
                                  "review_on": "2027-01-15",
                                  "milestones": [{"name": "Vault", "due": "2027-02-01"}]})
    replaced = pulled.patch(f"/risks/{risk['id']}", {"milestones": []}, risk["modified"])
    assert replaced["milestones"] == []


def test_mapping_reviews(pulled: Api):
    library_mapping = "mapping--ogrc-ac-02_to_nist-sp-800-53-r5-ac-2_part_j"
    mapping = pulled.get(f"/mappings/{library_mapping}")
    review = pulled.post("/mapping-reviews", {"mapping_ref": library_mapping,
                                              "review_status": "reviewed"})
    assert review["library_version"] == "0.1.0"
    assert review["mapping_modified"] == mapping["modified"]
    pulled.post("/mapping-reviews", {"mapping_ref": library_mapping, "review_status": "rejected"},
                expect=409)
    own = pulled.post("/mappings", {"source_ref": C1, "target_ref": AC2,
                                    "relationship": "subset-of"})
    pulled.post("/mapping-reviews", {"mapping_ref": own["id"], "review_status": "reviewed"},
                expect=400)
    listed = pulled.get(f"/mapping-reviews?mapping_id={library_mapping}")["data"]
    assert [r["id"] for r in listed] == [review["id"]]


def test_effective_baseline(pulled: Api):
    custom = pulled.post("/controls", {"id": "control--com.acme.badge", "name": "Badge",
                                       "statement": "s", "objective": "o"})
    baseline = pulled.post("/baselines", {"name": "Acme", "extends_ref": LIB_BASELINE,
                                          "control_refs": [custom["id"]],
                                          "parameter_bindings": {C1: {"shared_account_review": "monthly"}}})
    effective = pulled.get(f"/baselines/{baseline['id']}/effective")
    assert effective["control_ids"] == [C1, C2, custom["id"]]
    assert set(effective["requirement_ids"]) == {AC2, "requirement--nist-sp-800-53-r5-ac-3"}
    assert effective["parameter_bindings"][C1] == {"shared_account_review": "monthly"}
    nested = pulled.post("/baselines", {"name": "x", "extends_ref": baseline["id"]}, expect=400)
    assert nested["errors"][0]["pointer"] == "/extends_ref"
