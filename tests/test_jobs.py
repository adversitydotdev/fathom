"""Jobs: library pull, provider import, the harness, renders, git export, and restore."""

import io
import json
import subprocess
from pathlib import Path

import yaml

from fathom.adapters.library import DirectoryLibrary
from fathom.operations.exports import ExportSettings
from tests.conftest import (
    AC2,
    C1,
    C2,
    LIB_BASELINE,
    LIB_TEST,
    STAMP,
    Api,
    library_objects,
    write_library,
)

ENV = {"spec_version": "0.1.0", "created": STAMP, "modified": STAMP}


# --- library pull --------------------------------------------------------------------------


def test_pull_pins_and_a_later_revision_revokes_missing_ids(make_app, tmp_path: Path):
    v1 = write_library(tmp_path / "v1", library_objects(), "0.1.0")
    objects = [o for o in library_objects() if o["id"] != C2]
    for o in objects:
        if o["id"] == LIB_BASELINE:
            o["control_refs"] = [C1]
        if o["id"] == "mapping--ogrl-ac-01_to_nist-sp-800-53-r5-ac-2_part_a":
            o["modified"] = "2026-11-01T00:00:00Z"
            o["relationship"] = "subset-of"
    objects = [o for o in objects if o.get("source_ref") != C2]
    v2 = write_library(tmp_path / "v2", objects, "0.2.0")

    client, c = make_app(library_source=DirectoryLibrary(v1, "one"))
    admin = Api(client, "administrator")
    assert admin.get("/library") == {}
    job = admin.post("/library/pull", {"version": "0.1.0"}, expect=202)
    assert job["status"] == "succeeded" and job["report"]["added"] == 10
    assert admin.get("/library") == {
        "id": "bundle--ogrl-library",
        "version": "0.1.0",
        "commit": "one",
    }
    review = admin.post(
        "/mapping-reviews",
        {
            "mapping_ref": "mapping--ogrl-ac-01_to_nist-sp-800-53-r5-ac-2_part_a",
            "review_status": "reviewed",
        },
    )
    wrong = admin.post("/library/pull", {"version": "9.9.9"}, expect=202)
    assert wrong["status"] == "failed" and admin.get("/library")["version"] == "0.1.0"

    object.__setattr__(c.library, "_source", DirectoryLibrary(v2, "two"))
    job = admin.post("/library/pull", {"version": "0.2.0"}, expect=202)
    assert job["status"] == "succeeded", job
    assert C2 in job["report"]["revoked"]
    assert job["report"]["stale_reviews"] == [review["id"]]
    gone = admin.get(f"/controls/{C2}")
    assert gone["revoked"] is True  # kept so references still resolve
    assert all(c["id"] != C2 for c in admin.get("/controls")["data"])


def test_pull_leaves_organization_objects_alone(pulled: Api, program):
    impl = pulled.post(
        "/implementations",
        {
            "system_ref": program["system"],
            "control_ref": C1,
            "status": "planned",
            "responsibility": "provider",
            "parameter_values": {"shared_account_review": "weekly"},
        },
    )
    pulled.post("/library/pull", {"version": "0.1.0"}, expect=202)
    assert pulled.get(f"/implementations/{impl['id']}") == impl


# --- providers ------------------------------------------------------------------------------


def provider_bundle(path: Path, *, with_row: bool = True) -> Path:
    objects = [
        {
            "type": "party",
            "id": "party--com.example",
            **ENV,
            "name": "Example",
            "kind": "organization",
        },
        {
            "type": "component",
            "id": "component--com.example.cloud-idp",
            **ENV,
            "name": "Cloud IdP",
            "kind": "service",
            "party_ref": "party--com.example",
        },
    ]
    if with_row:
        objects.append(
            {
                "type": "implementation",
                "id": "implementation--com.example.cloud-idp-ogrl-ac-01",
                **ENV,
                "component_ref": "component--com.example.cloud-idp",
                "control_ref": C1,
                "status": "implemented",
                "responsibility": "shared",
                "narrative": "One identity per person.",
                "customer_responsibility": "Review guests.",
            }
        )
    path.write_text(
        yaml.safe_dump(
            {
                "type": "bundle",
                "id": "bundle--com.example.cloud-idp",
                **ENV,
                "name": "Example Cloud IdP",
                "version": "2026.11",
                "library": {"id": "bundle--ogrl-library", "version": "0.1.0"},
                "objects": objects,
            }
        )
    )
    return path


def test_provider_import_is_a_read_only_projection(pulled: Api, program, tmp_path: Path):
    bundle = provider_bundle(tmp_path / "idp.yaml")
    job = pulled.post("/providers", {"kind": "ogrl", "url": str(bundle)}, expect=202)
    assert job["status"] == "succeeded", job
    pin = pulled.get("/providers/bundle--com.example.cloud-idp")
    assert pin["version"] == "2026.11" and pin["digest"].startswith("sha-256:")
    row = pulled.get("/implementations/implementation--com.example.cloud-idp-ogrl-ac-01")
    assert row["origin"] == "provider"
    problem = pulled.patch(
        f"/implementations/{row['id']}", {"narrative": "x"}, row["modified"], expect=409
    )
    assert problem["type"].endswith("provider-object")
    listed = pulled.get("/components?provider_id=bundle--com.example.cloud-idp")["data"]
    assert [c["id"] for c in listed] == ["component--com.example.cloud-idp"]

    # Attaching the component is the organization's own edit. The shared row is the
    # provider's half; the control stays a gap until the organization writes its half.
    system = pulled.get(f"/systems/{program['system']}")
    pulled.patch(
        f"/systems/{system['id']}",
        {"component_refs": ["component--com.example.cloud-idp"]},
        system["modified"],
    )
    status = pulled.get(f"/programs/{program['program']}/status")
    c1 = next(c for c in status["controls"] if c["control_id"] == C1)
    assert c1["state"] == "gap" and "organization's implementation is missing" in c1["failed"][0]

    # A re-import without the row revokes it and keeps it resolvable.
    provider_bundle(bundle, with_row=False)
    job = pulled.post("/providers", {"kind": "ogrl", "url": str(bundle)}, expect=202)
    assert job["report"]["revoked"] == [row["id"]]
    assert pulled.get(f"/implementations/{row['id']}")["revoked"] is True


def test_provider_import_refusals(pulled: Api, tmp_path: Path):
    bundle = provider_bundle(tmp_path / "idp.yaml")
    job = pulled.post(
        "/providers", {"kind": "ogrl", "url": str(bundle), "digest": "sha-256:00"}, expect=202
    )
    assert job["status"] == "failed" and "sha-256" in job["error"]["detail"]
    data = yaml.safe_load(bundle.read_text())
    data["objects"][0]["id"] = "party--example"  # the library's slug space
    bundle.write_text(yaml.safe_dump(data))
    job = pulled.post("/providers", {"kind": "ogrl", "url": str(bundle)}, expect=202)
    assert job["status"] == "failed" and "standard-library" in job["error"]["detail"]


def test_oscal_component_definition_import(pulled: Api, tmp_path: Path):
    document = {
        "component-definition": {
            "uuid": "8a7f0d5c-0000-4000-8000-000000000001",
            "metadata": {
                "title": "Django",
                "version": "1.0",
                "last-modified": STAMP,
                "parties": [
                    {
                        "uuid": "8a7f0d5c-0000-4000-8000-000000000002",
                        "type": "organization",
                        "name": "Django Software Foundation",
                    }
                ],
            },
            "components": [
                {
                    "uuid": "8a7f0d5c-0000-4000-8000-000000000003",
                    "type": "software",
                    "title": "Django",
                    "description": "Web framework.",
                    "control-implementations": [
                        {
                            "uuid": "8a7f0d5c-0000-4000-8000-000000000004",
                            "source": "https://raw.githubusercontent.com/usnistgov/oscal-content/main/nist.gov/SP800-53/rev5/json/NIST_SP-800-53_rev5_catalog.json",
                            "description": "800-53",
                            "implemented-requirements": [
                                {
                                    "uuid": "8a7f0d5c-0000-4000-8000-000000000005",
                                    "control-id": "ac-2",
                                    "description": "Accounts.",
                                    "props": [{"name": "security_control_type", "value": "Hybrid"}],
                                },
                                {
                                    "uuid": "8a7f0d5c-0000-4000-8000-000000000006",
                                    "control-id": "ac-3",
                                    "description": "Enforcement.",
                                    "props": [{"name": "provider", "value": "No"}],
                                },
                                {
                                    "uuid": "8a7f0d5c-0000-4000-8000-000000000007",
                                    "control-id": "zz-9",
                                    "description": "Unknown.",
                                },
                            ],
                        }
                    ],
                }
            ],
        }
    }
    path = tmp_path / "django.json"
    path.write_text(json.dumps(document))
    job = pulled.post("/providers", {"kind": "oscal-component", "url": path.as_uri()}, expect=202)
    assert job["status"] == "succeeded", job
    assert any("zz-9" in w for w in job["report"]["warnings"])
    rows = pulled.get("/implementations?origin=provider")["data"]
    assert {(r["requirement_ref"], r["responsibility"]) for r in rows} == {
        (AC2, "shared"),
        ("requirement--nist-sp-800-53-r5-ac-3", "customer"),
    }


# --- harness -------------------------------------------------------------------------------


def run_test(api: Api, program, command: str, **run) -> dict:
    impl = api.get(f"/implementations?control_id={C1}")["data"]
    impl = (
        impl[0]
        if impl
        else api.post(
            "/implementations",
            {
                "system_ref": program["system"],
                "control_ref": C1,
                "status": "implemented",
                "responsibility": "provider",
            },
        )
    )
    test = api.post(
        "/tests",
        {
            "name": "t",
            "control_ref": C1,
            "method": "automated",
            "fulfills_ref": LIB_TEST,
            "run": {"runner": "shell", "command": command, **run},
        },
    )
    job = api.post(f"/tests/{test['id']}/runs", {"implementation_id": impl["id"]}, expect=202)
    assert job["status"] == "succeeded", job
    return api.get(f"/results/{job['result_id']}")


def test_harness_maps_exit_codes_and_environment(pulled: Api, program):
    result = run_test(
        pulled,
        program,
        'echo "$IDP_TENANT $OGRL_CONTROL_ID $OGRL_PARAM_SHARED_ACCOUNT_REVIEW"',
        env=["IDP_TENANT"],
    )
    assert result["outcome"] == "pass"
    assert result["summary"] == f"acme {C1} quarterly"
    assert run_test(pulled, program, "echo nope; exit 1")["outcome"] == "fail"
    assert run_test(pulled, program, "exit 3")["outcome"] == "error"
    missing = run_test(pulled, program, "true", env=["NOT_CONFIGURED"])
    assert missing["outcome"] == "error" and "NOT_CONFIGURED" in missing["summary"]
    evidence = run_test(
        pulled,
        program,
        "true",
        evidence=[{"path": "out.txt", "name": "o", "media_type": "text/plain"}],
    )
    assert evidence["outcome"] == "error" and "missing" in evidence["summary"]
    timeout = run_test(pulled, program, "sleep 5", timeout="1s")
    assert timeout["outcome"] == "error" and "timed out" in timeout["summary"]
    leaked = run_test(
        pulled, program, 'echo "${HOME_DIRECTORY_SECRET:-clean} ${VIRTUAL_ENV:-clean}"'
    )
    assert leaked["summary"] == "clean clean"


def test_run_refusals(pulled: Api, program):
    pulled.post(f"/tests/{LIB_TEST}/runs", {"implementation_id": "implementation--x"}, expect=400)
    pulled.post("/tests/test--com.acme.nope/runs", {"implementation_id": "x"}, expect=404)
    custom = pulled.post(
        "/tests",
        {
            "name": "t",
            "control_ref": C1,
            "method": "automated",
            "run": {"runner": "lambda", "command": "x"},
        },
    )
    impl = pulled.post(
        "/implementations",
        {
            "system_ref": program["system"],
            "control_ref": C1,
            "status": "planned",
            "responsibility": "provider",
        },
    )
    bad = pulled.post(f"/tests/{custom['id']}/runs", {"implementation_id": impl["id"]}, expect=400)
    assert bad["errors"][0]["pointer"] == "/run/runner"


# --- renders -------------------------------------------------------------------------------


def test_renders_produce_downloadable_files(pulled: Api, program):
    pulled.post(
        "/implementations",
        {
            "system_ref": program["system"],
            "control_ref": C1,
            "status": "implemented",
            "responsibility": "provider",
            "narrative": "Every person has one IdP account.",
        },
    )
    pulled.post(f"/programs/{program['program']}/renders", {"view": "oscal"}, expect=400)
    job = pulled.post(
        f"/programs/{program['program']}/renders",
        {"view": "oscal", "framework_id": "framework--nist-sp-800-53-r5"},
        expect=202,
    )
    assert job["status"] == "succeeded", job
    assert set(job["files"]) == {
        "profile.json",
        "ssp.json",
        "mapping-collection.json",
        "component-definition.json",
        "assessment-results.json",
        "poam.json",
    }
    ssp = pulled.get(f"/jobs/{job['id']}/files/ssp.json")
    plan = ssp["system-security-plan"]
    [req] = plan["control-implementation"]["implemented-requirements"]
    assert req["control-id"] == "ac-2"
    assert (
        req["props"][0]["value"] == "implemented"
    )  # equal-to, and the implementation is implemented
    assert "Every person has one IdP account." in req["remarks"]
    profile = pulled.get(f"/jobs/{job['id']}/files/profile.json")["profile"]
    assert profile["imports"][0]["include-controls"][0]["with-ids"] == ["ac-2"]
    assert profile["modify"]["set-parameters"] == [
        {"param-id": "ac_02_odp_10", "values": ["monthly"]}
    ]
    pulled.get(f"/jobs/{job['id']}/files/nope.json", expect=404)

    ssp_job = pulled.post(f"/programs/{program['program']}/renders", {"view": "ssp"}, expect=202)
    text = pulled.client.get(f"/v1/jobs/{ssp_job['id']}/files/ssp.md", headers=pulled.headers).text
    assert "OGRL-AC-01" in text and "Every person has one IdP account." in text
    assert pulled.get("/jobs?type=render")["data"]


# --- git export and restore ------------------------------------------------------------------


def git(*args: str, cwd: Path | None = None) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout


def test_export_then_restore_round_trips(make_app, tmp_path: Path, library_dir: Path):
    remote = tmp_path / "remote.git"
    git("init", "--bare", "--quiet", "-b", "main", str(remote))
    client, _ = make_app(export=ExportSettings(remote=str(remote)))
    admin = Api(client, "administrator")
    admin.post("/library/pull", {"version": "0.1.0"}, expect=202)
    owner = admin.post("/parties", {"name": "Lead", "kind": "role"})
    system = admin.post("/systems", {"name": "Prod"})
    admin.post("/programs", {"name": "P", "system_ref": system["id"], "baseline_ref": LIB_BASELINE})
    policy = admin.post(
        "/policies",
        {"name": "Access", "status": "draft", "owner_ref": owner["id"], "adopted": "2026-11-01"},
    )
    uploaded = client.post(
        f"/v1/policies/{policy['id']}/content",
        headers={**admin.headers, "If-Match": policy["modified"]},
        files={"file": ("p.md", io.BytesIO(b"# Access policy"), "text/markdown")},
    )
    admin.patch(f"/policies/{policy['id']}", {"status": "adopted"}, uploaded.json()["modified"])

    job = admin.post("/exports/git", expect=202)
    assert job["status"] == "succeeded" and job["report"]["changed"] is True, job
    again = admin.post("/exports/git", expect=202)
    assert again["report"]["changed"] is False

    checkout = tmp_path / "checkout"
    git("clone", "--quiet", str(remote), str(checkout))
    manifest = yaml.safe_load((checkout / "bundle.yaml").read_text())
    assert manifest["library"]["version"] == "0.1.0"
    _, remainder = policy["id"].split("--", 1)
    assert (checkout / "policy" / f"{remainder}.body").read_bytes() == b"# Access policy"
    assert not (checkout / "control").exists()  # library bodies stay in the library repo

    fresh, _ = make_app()
    restorer = Api(fresh, "administrator")
    job = restorer.post("/restore", {"url": str(remote)}, expect=202)
    assert job["status"] == "succeeded", job
    assert job["report"]["missing_bytes"] == []
    assert restorer.get(f"/systems/{system['id']}") == admin.get(f"/systems/{system['id']}")
    assert restorer.get(f"/policies/{policy['id']}") == admin.get(f"/policies/{policy['id']}")
    body = fresh.get(f"/v1/policies/{policy['id']}/content", headers=restorer.headers)
    assert body.content == b"# Access policy"
    restorer.post("/restore", {"url": str(remote)}, expect=409)  # no longer empty
    early = restorer.get(f"/programs?system_id={system['id']}")["data"][0]
    restorer.get(f"/programs/{early['id']}/status?at=2026-01-01T00:00:00Z", expect=400)

    # A commit the job did not write stops the next export.
    git("config", "user.email", "x@example.com", cwd=checkout)
    git("config", "user.name", "x", cwd=checkout)
    (checkout / "README").write_text("hand edit")
    git("add", "README", cwd=checkout)
    git("commit", "--quiet", "-m", "hand", cwd=checkout)
    git("push", "--quiet", "origin", "HEAD:main", cwd=checkout)
    admin.post("/parties", {"name": "Another", "kind": "team"})
    job = admin.post("/exports/git", expect=202)
    assert job["status"] == "failed" and job["error"]["type"].endswith("export-diverged")
    problem = admin.post("/exports/git", expect=409)
    assert problem["type"].endswith("export-diverged")


def test_export_is_a_disabled_feature_without_a_remote(admin: Api):
    problem = admin.post("/exports/git", expect=404)
    assert problem["type"].endswith("feature-disabled")


def test_restore_refuses_a_broken_graph(make_app, tmp_path: Path):
    snapshot = {
        "type": "bundle",
        "id": "bundle--com.acme.org",
        **ENV,
        "name": "Acme",
        "version": STAMP,
        "library": {"id": "bundle--ogrl-library", "version": "0.1.0", "commit": "c0ffee"},
        "objects": [
            {
                "type": "program",
                "id": "program--com.acme.p",
                **ENV,
                "name": "P",
                "system_ref": "system--com.acme.missing",
                "baseline_ref": LIB_BASELINE,
            }
        ],
    }
    path = tmp_path / "snapshot.json"
    path.write_text(json.dumps(snapshot))
    client, _ = make_app()
    admin = Api(client, "administrator")
    job = admin.post("/restore", {"url": str(path)}, expect=202)
    assert job["status"] == "failed"
    assert "program--com.acme.p/system_ref" in job["error"]["detail"]
    assert admin.get("/library") == {}  # a refused restore leaves the database empty
