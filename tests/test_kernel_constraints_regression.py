"""Regression tests for RFC 0001 §7.20 graph constraints (drift audit)."""

from fathom.kernel import constraints
from fathom.kernel.graph import Graph
from fathom.kernel.models import Implementation, Mapping, parse
from tests.conftest import AC2, C1, STAMP, library_objects


def graph(*extra: dict) -> Graph:
    lib = library_objects()
    objs = [parse(o) for o in (*lib, *extra)]
    return Graph(objs, library_ids=[o["id"] for o in lib])


def test_provider_shared_or_customer_requires_customer_responsibility():
    base = {
        "id": "implementation--provider-shared-missing",
        "created": STAMP,
        "modified": STAMP,
        "control_ref": C1,
        "component_ref": "component--com.example.cloud-idp",
        "status": "implemented",
        "origin": "provider",
        "responsibility": "shared",
        "narrative": "Provider half only.",
    }
    impl = Implementation.model_validate(base)
    support = [
        {
            "type": "component",
            "id": "component--com.example.cloud-idp",
            "created": STAMP,
            "modified": STAMP,
            "name": "Cloud IdP",
            "kind": "service",
            "party_ref": "party--example",
        },
        {
            "type": "party",
            "id": "party--example",
            "created": STAMP,
            "modified": STAMP,
            "name": "Example",
            "kind": "organization",
        },
    ]
    violations = constraints.check(impl, graph(*support), origin="provider")
    assert any(v.pointer == "/customer_responsibility" for v in violations)

    ok = Implementation.model_validate(
        {
            **base,
            "system_ref": None,
            "component_ref": "component--com.example.cloud-idp",
            "customer_responsibility": "Customer enrolls MFA.",
        }
    )
    g = graph(*support)
    pointers = {v.pointer for v in constraints.check(ok, g, origin="provider")}
    assert "/customer_responsibility" not in pointers


def test_oscal_style_provider_row_may_omit_customer_responsibility():
    """RFC 0001 §7.20: OSCAL component imports may omit customer_responsibility."""
    row = Implementation.model_validate(
        {
            "id": "implementation--oscal-shared",
            "created": STAMP,
            "modified": STAMP,
            "requirement_ref": AC2,
            "component_ref": "component--com.example.cloud-idp",
            "status": "implemented",
            "origin": "provider",
            "responsibility": "shared",
            "narrative": "Accounts.",
        }
    )
    support = [
        {
            "type": "component",
            "id": "component--com.example.cloud-idp",
            "created": STAMP,
            "modified": STAMP,
            "name": "Cloud IdP",
            "kind": "service",
            "party_ref": "party--example",
        },
        {
            "type": "party",
            "id": "party--example",
            "created": STAMP,
            "modified": STAMP,
            "name": "Example",
            "kind": "organization",
        },
    ]
    pointers = {v.pointer for v in constraints.check(row, graph(*support), origin="provider")}
    assert "/customer_responsibility" not in pointers


def test_revoked_mapping_does_not_block_duplicate_source_target_pair():
    revoked = {
        "type": "mapping",
        "id": "mapping--org-revoked",
        "created": STAMP,
        "modified": STAMP,
        "revoked": True,
        "source_ref": C1,
        "target_ref": f"{AC2}#j",
        "relationship": "subset-of",
    }
    replacement = Mapping.model_validate(
        {
            "id": "mapping--org-replacement",
            "created": STAMP,
            "modified": STAMP,
            "source_ref": C1,
            "target_ref": f"{AC2}#j",
            "relationship": "equal-to",
        }
    )
    assert constraints.check(replacement, graph(revoked)) == []

    live = {
        "type": "mapping",
        "id": "mapping--org-live",
        "created": STAMP,
        "modified": STAMP,
        "source_ref": C1,
        "target_ref": f"{AC2}#j",
        "relationship": "subset-of",
    }
    duplicate = Mapping.model_validate(
        {
            "id": "mapping--org-duplicate",
            "created": STAMP,
            "modified": STAMP,
            "source_ref": C1,
            "target_ref": f"{AC2}#j",
            "relationship": "subset-of",
        }
    )
    violations = constraints.check(duplicate, graph(live))
    assert any(v.pointer == "/target_ref" for v in violations)
