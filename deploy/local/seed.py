#!/usr/bin/env python3
# ruff: noqa: E501
"""Idempotent local development seeder for the Fathom Docker Compose stack.

Pulls `ogrl-library` (default v0.4.1) and populates a starter organization ("Acme Platform")
with two live programs (NIST 800-171 r3 & SOC 2), implementations, results,
evidence, risks, an exception, a finding, policies, and procedures so the UI
opens straight into real Postgres + ogrl-rs kernel data.

Set FATHOM_SKIP_SEED=true to boot an empty workspace instead.
Set FATHOM_SEED_LIBRARY_COMMIT to pull by git revision (e.g. main) before a library-v* tag
exists for spec 0.2.0; otherwise FATHOM_SEED_LIBRARY_VERSION selects a tagged release.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime, timedelta

API = os.environ.get("FATHOM_API_ORIGIN", "http://api:8080").rstrip("/")
TOKEN = os.environ.get("FATHOM_API_TOKEN", "fathom_pat_local_dev_admin")
LIB_VERSION = os.environ.get("FATHOM_SEED_LIBRARY_VERSION", "0.4.1")
LIB_COMMIT = os.environ.get("FATHOM_SEED_LIBRARY_COMMIT")


def req(method: str, path: str, body: dict | None = None, *, if_match: str | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Authorization": f"Bearer {TOKEN}", "Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    if if_match is not None:
        headers["If-Match"] = if_match
    r = urllib.request.Request(f"{API}{path}", data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(r, timeout=30) as resp:
            raw = resp.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        raise RuntimeError(f"{method} {path} -> HTTP {exc.code}: {detail}") from exc


def upload_markdown(path: str, markdown: str, *, if_match: str) -> dict:
    boundary = "----OGRLSeedBoundary7MA4YWxkTrZu0gW"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="document.md"\r\n'
        f"Content-Type: text/markdown\r\n\r\n"
        f"{markdown}\r\n"
        f"--{boundary}--\r\n"
    ).encode()
    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "Accept": "application/json",
        "Content-Type": f"multipart/form-data; boundary={boundary}",
        "If-Match": if_match,
    }
    r = urllib.request.Request(f"{API}{path}", data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(r, timeout=30) as resp:
            raw = resp.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        raise RuntimeError(f"POST {path} -> HTTP {exc.code}: {detail}") from exc


def create_adopted_doc(
    collection: str, payload: dict, body_md: str, adopted_date: str | None = None
) -> str:
    draft = req("POST", f"/v1/{collection}", {**payload, "status": "draft"})
    uploaded = upload_markdown(
        f"/v1/{collection}/{draft['id']}/content",
        body_md,
        if_match=draft["modified"],
    )
    patch: dict = {"status": "adopted"}
    if adopted_date:
        patch["adopted"] = adopted_date
    req("PATCH", f"/v1/{collection}/{draft['id']}", patch, if_match=uploaded["modified"])
    return draft["id"]


def wait_for_health() -> None:
    for _ in range(60):
        try:
            with urllib.request.urlopen(f"{API}/health", timeout=3) as resp:
                if resp.status == 200:
                    return
        except Exception:
            time.sleep(1)
    raise RuntimeError(f"API at {API}/health did not become ready in time")


def wait_for_job(job_id: str) -> dict:
    for _ in range(180):
        job = req("GET", f"/v1/jobs/{job_id}")
        status = job.get("status")
        if status == "succeeded":
            return job
        if status == "failed":
            raise RuntimeError(f"Job {job_id} failed: {job.get('error')}")
        time.sleep(1)
    raise RuntimeError(f"Job {job_id} timed out")


def iso_day(offset: int) -> str:
    return (datetime.now(UTC) + timedelta(days=offset)).strftime("%Y-%m-%d")


def iso_ts(offset: int) -> str:
    return (datetime.now(UTC) + timedelta(days=offset)).strftime("%Y-%m-%dT09:00:00Z")


# First-party integration releases (RFC 0005 section 4), pinned to their published sha-256.
INTEGRATIONS = [
    (
        "dev.adversity.okta",
        "0.1.4",
        "https://github.com/adversitydotdev/ogrl-okta/releases/download/v0.1.4/dev.adversity.okta-0.1.4.tar.gz",
        "d6d6a16eed701c58d2dc6bcabeb51c81ca1220515a7afbe295c79424802e8a95",
    ),
    (
        "dev.adversity.aws",
        "0.3.0",
        "https://github.com/adversitydotdev/ogrl-aws/releases/download/v0.3.0/dev.adversity.aws-0.3.0.tar.gz",
        "13dd1dd94be32c7e75c762adbc0c4b42956d664d5ca5b8fc2ff1e10b83d66033",
    ),
    (
        "dev.adversity.github",
        "0.1.2",
        "https://github.com/adversitydotdev/ogrl-github/releases/download/v0.1.2/dev.adversity.github-0.1.2.tar.gz",
        "d5542667c8f5a35c4551f1e5864c79967597d28bfb6dcbf1849b1fbc06658f8e",
    ),
]


def install_integrations() -> None:
    """Install each release not already installed. A failure is reported, not fatal."""
    if os.environ.get("FATHOM_SEED_INTEGRATIONS", "true").lower() in {"0", "false", "no"}:
        return
    installed = {(i["id"], i["version"]) for i in req("GET", "/v1/integrations").get("data", [])}
    for integration_id, version, url, digest in INTEGRATIONS:
        if (integration_id, version) in installed:
            print(f"seed: {integration_id} {version} is installed.")
            continue
        try:
            job = req("POST", "/v1/integrations", {"url": url, "digest": digest, "enable": True})
            wait_for_job(job["id"])
            print(f"seed: installed {integration_id} {version}.")
        except RuntimeError as exc:
            print(f"seed: could not install {integration_id} {version}: {exc}", file=sys.stderr)


def main() -> int:
    if os.environ.get("FATHOM_SKIP_SEED", "").lower() in {"1", "true", "yes"}:
        print("seed: FATHOM_SKIP_SEED is set; skipping local seed.")
        return 0

    wait_for_health()
    install_integrations()

    existing = req("GET", "/v1/programs?limit=1")
    if existing.get("data"):
        print("seed: programs already exist; nothing to do.")
        return 0

    if LIB_COMMIT:
        print(f"seed: pulling ogrl-library at commit {LIB_COMMIT}...")
        job = req("POST", "/v1/library/pull", {"commit": LIB_COMMIT})
    else:
        print(f"seed: pulling ogrl-library v{LIB_VERSION}...")
        job = req("POST", "/v1/library/pull", {"version": LIB_VERSION})
    wait_for_job(job["id"])
    label = f"commit {LIB_COMMIT}" if LIB_COMMIT else f"v{LIB_VERSION}"
    print(f"seed: library {label} pulled (job {job['id']}).")

    # Parties
    jordan = req("POST", "/v1/parties", {"name": "Jordan Lee", "kind": "person"})["id"]
    priya = req("POST", "/v1/parties", {"name": "Priya Shah", "kind": "person"})["id"]
    platform = req("POST", "/v1/parties", {"name": "Platform engineering", "kind": "team"})["id"]
    secops = req("POST", "/v1/parties", {"name": "Security operations", "kind": "team"})["id"]
    okta_org = req("POST", "/v1/parties", {"name": "Okta, Inc.", "kind": "organization"})["id"]
    aws_org = req("POST", "/v1/parties", {"name": "Amazon Web Services", "kind": "organization"})[
        "id"
    ]
    req("POST", "/v1/parties", {"name": "Compliance agent", "kind": "role", "tags": ["agent"]})

    # Components & System
    okta_comp = req(
        "POST",
        "/v1/components",
        {"name": "Okta Workforce Identity", "kind": "service", "party_ref": okta_org},
    )["id"]
    aws_comp = req(
        "POST",
        "/v1/components",
        {"name": "AWS (us-east-1)", "kind": "service", "party_ref": aws_org},
    )["id"]

    system_id = req(
        "POST",
        "/v1/systems",
        {
            "name": "Acme Platform",
            "function": "Multi-tenant SaaS storing and processing customer engineering data, including CUI.",
            "boundary": "Production AWS account 4471, the Okta tenant, and CI/CD deployment pipelines.",
            "component_refs": [okta_comp, aws_comp],
            "information_types": [
                {
                    "name": "Controlled unclassified information",
                    "confidentiality": "moderate",
                    "integrity": "moderate",
                    "availability": "low",
                }
            ],
            "parties": [
                {
                    "party_ref": aws_org,
                    "role": "subservice",
                    "function": "Hosting and physical security",
                },
                {"party_ref": okta_org, "role": "subservice", "function": "Workforce identity"},
                {"party_ref": platform, "role": "operator"},
            ],
        },
    )["id"]

    # Programs bound to library baselines (IDs from the pinned ogrl-library release)
    req(
        "POST",
        "/v1/programs",
        {
            "name": "NIST 800-171 r3",
            "system_ref": system_id,
            "baseline_ref": "baseline--ogrl-nist-800-171-r3",
        },
    )
    req(
        "POST",
        "/v1/programs",
        {
            "name": "SOC 2 Core",
            "system_ref": system_id,
            "baseline_ref": "baseline--ogrl-soc2",
        },
    )

    # Implementations across baseline controls
    impl_specs = [
        (
            "control--ogrl-ac-01",
            "implemented",
            "provider",
            jordan,
            "HRIS joiner/mover/leaver events drive Okta provisioning and revoke sessions within 24 hours.",
            {"approver_role": "engineering manager", "deprovision_sla": "24 hours"},
            "pass",
            "test--ogrl-ac-01-lifecycle",
        ),
        (
            "control--ogrl-ac-02",
            "implemented",
            "provider",
            jordan,
            "Quarterly access certifications run in Okta Access Governance for all privileged groups.",
            None,
            "pass",
            "test--ogrl-ac-02-access-review",
        ),
        (
            "control--ogrl-ac-03",
            "implemented",
            "provider",
            platform,
            "Production access is granted via time-boxed AWS IAM Identity Center permission sets.",
            None,
            "pass",
            "test--ogrl-ac-03-least-privilege",
        ),
        (
            "control--ogrl-ac-05",
            "implemented",
            "shared",
            jordan,
            "Okta enforces WebAuthn security keys for Admins and Break-glass groups.",
            {"mfa_standard": "phishing-resistant (FIDO2/WebAuthn)"},
            "fail",
            "test--ogrl-ac-05-mfa-enforcement",
        ),
        (
            "control--ogrl-lm-01",
            "implemented",
            "provider",
            secops,
            "CloudTrail organization trail, VPC flow logs, and Okta System Log stream to the SIEM.",
            None,
            "pass",
            "test--ogrl-lm-01-audit-logging",
        ),
        (
            "control--ogrl-cm-01",
            "partial",
            "provider",
            platform,
            "GitHub branch protection requires approving review and passing CI on main.",
            None,
            None,
            "test--ogrl-cm-01-change-control",
        ),
        (
            "control--ogrl-cr-01",
            "implemented",
            "provider",
            platform,
            "RDS, S3, and EBS use KMS CMKs; external and internal traffic enforces TLS 1.2+.",
            None,
            "pass",
            "test--ogrl-cr-01-encryption",
        ),
        (
            "control--ogrl-ir-01",
            "exception",
            "provider",
            secops,
            "Incident response tabletop exercise deferred pending Q1 multi-region failover cutover.",
            None,
            None,
            "test--ogrl-ir-01-ir-testing",
        ),
        (
            "control--ogrl-vm-01",
            "implemented",
            "provider",
            secops,
            "AWS Inspector scans hosts and ECR images continuously; Dependabot covers app dependencies.",
            None,
            "fail",
            "test--ogrl-vm-01-vuln-scanning",
        ),
    ]

    tests_by_id = {t["id"]: t for t in req("GET", "/v1/tests?limit=200").get("data", [])}

    impl_ids: dict[str, str] = {}
    for ctrl_id, status, resp, owner, narrative, params, outcome, test_id in impl_specs:
        payload: dict = {
            "system_ref": system_id,
            "control_ref": ctrl_id,
            "status": status,
            "responsibility": resp,
            "origin": "organization",
            "owner_ref": owner,
            "narrative": narrative,
        }
        if params:
            payload["parameter_values"] = params
        impl_id = req("POST", "/v1/implementations", payload)["id"]
        impl_ids[ctrl_id] = impl_id

        res_id: str | None = None
        test_obj = tests_by_id.get(test_id)
        if outcome and test_obj and test_obj.get("method") == "manual":
            summary = None
            if outcome == "fail" and ctrl_id == "control--ogrl-ac-05":
                summary = "2 of 14 privileged users still have SMS fallback enrolled."
            elif outcome == "fail" and ctrl_id == "control--ogrl-vm-01":
                summary = "3 critical CVEs open past 15-day SLA on ECR image api:2026.10."
            res_payload: dict = {
                "test_ref": test_id,
                "implementation_ref": impl_id,
                "observed": iso_ts(-1),
                "outcome": outcome,
            }
            if summary:
                res_payload["summary"] = summary
            res_id = req("POST", "/v1/results", res_payload)["id"]

        if outcome:
            ev_payload: dict = {
                "name": f"{ctrl_id.replace('control--', '')} verification record",
                "method": "attestation",
                "collected": iso_ts(-1),
                "valid_from": iso_day(-1),
                "valid_until": iso_day(90 if outcome == "pass" else 14),
                "implementation_ref": impl_id,
                "resource": {
                    "uri": f"https://internal.acme.example/evidence/{ctrl_id}",
                    "media_type": "application/json",
                },
            }
            if res_id:
                ev_payload["result_ref"] = res_id
            req("POST", "/v1/evidence", ev_payload)

    # Risks
    ir_risk_id = req(
        "POST",
        "/v1/risks",
        {
            "name": "Incident response tabletop overdue during migration",
            "system_ref": system_id,
            "statement": "The annual tabletop exercise is deferred until multi-region failover lands.",
            "likelihood": 3,
            "impact": 4,
            "residual_likelihood": 2,
            "residual_impact": 4,
            "treatment": "mitigate",
            "status": "treating",
            "owner_ref": secops,
            "control_refs": ["control--ogrl-ir-01"],
            "milestones": [
                {"name": "Finish multi-region cutover", "due": iso_day(25)},
                {"name": "Run incident tabletop", "due": iso_day(40)},
            ],
        },
    )["id"]
    req(
        "POST",
        "/v1/risks",
        {
            "name": "Privileged users can fall back to SMS MFA",
            "system_ref": system_id,
            "statement": "Two administrators still have SMS enrolled, risking SIM-swap session takeover.",
            "likelihood": 2,
            "impact": 5,
            "treatment": "mitigate",
            "status": "open",
            "owner_ref": jordan,
            "control_refs": ["control--ogrl-ac-05"],
        },
    )
    req(
        "POST",
        "/v1/risks",
        {
            "name": "Production container images carry unpatched critical CVEs",
            "system_ref": system_id,
            "statement": "Base images older than the 15-day SLA are still serving traffic.",
            "likelihood": 3,
            "impact": 3,
            "treatment": "mitigate",
            "status": "open",
            "owner_ref": platform,
            "control_refs": ["control--ogrl-vm-01"],
        },
    )

    # Exception & Finding
    req(
        "POST",
        "/v1/exceptions",
        {
            "implementation_ref": impl_ids["control--ogrl-ir-01"],
            "justification": "Tabletop resumes immediately after Q1 multi-region failover cutover.",
            "expires": iso_day(22),
            "approver_ref": priya,
            "risk_ref": ir_risk_id,
        },
    )
    req(
        "POST",
        "/v1/findings",
        {
            "name": "SMS MFA fallback still enabled for two privileged accounts",
            "system_ref": system_id,
            "objective_ref": "requirement--nist-sp-800-171-r3-03-05-03#obj.01",
            "determination": "not-satisfied",
            "observed": iso_day(-3),
            "narrative": "Okta authentication policy permitted SMS fallback for two legacy admin accounts.",
            "implementation_ref": impl_ids["control--ogrl-ac-05"],
        },
    )

    # Policies & Procedures (adopted documents upload content to S3 first so resource.digest is set)
    infosec_pol = create_adopted_doc(
        "policies",
        {
            "name": "Information Security Policy",
            "version": "2.3",
            "owner_ref": priya,
            "reviewed": iso_day(-20),
            "review_interval": "annual",
            "control_refs": ["control--ogrl-ac-01", "control--ogrl-cr-01"],
        },
        "# Information Security Policy v2.3\n\nAcme protects customer data and CUI across Acme Platform.\n",
        adopted_date=iso_day(-180),
    )
    access_pol = create_adopted_doc(
        "policies",
        {
            "name": "Access Control & Identity Policy",
            "version": "1.8",
            "owner_ref": jordan,
            "reviewed": iso_day(-15),
            "review_interval": "annual",
            "control_refs": ["control--ogrl-ac-01", "control--ogrl-ac-02", "control--ogrl-ac-05"],
        },
        "# Access Control & Identity Policy v1.8\n\nAll workforce and privileged accounts enforce phishing-resistant MFA.\n",
        adopted_date=iso_day(-150),
    )
    req(
        "POST",
        "/v1/policies",
        {
            "name": "Production Change Control Policy",
            "status": "draft",
            "version": "0.9",
            "owner_ref": platform,
            "control_refs": ["control--ogrl-cm-01"],
        },
    )
    create_adopted_doc(
        "procedures",
        {
            "name": "Quarterly Access Certification Runbook",
            "policy_ref": access_pol,
            "owner_ref": jordan,
            "control_refs": ["control--ogrl-ac-02", "control--ogrl-ac-03"],
        },
        "# Quarterly Access Certification Runbook\n\nReview privileged Okta and AWS Identity Center entitlements quarterly.\n",
    )
    create_adopted_doc(
        "procedures",
        {
            "name": "Vulnerability Triage & Patching SLA",
            "policy_ref": infosec_pol,
            "owner_ref": secops,
            "control_refs": ["control--ogrl-vm-01"],
        },
        "# Vulnerability Triage & Patching SLA\n\nRemediate critical CVEs within 15 days and high CVEs within 30 days.\n",
    )

    print("seed: local development workspace seeded cleanly.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
