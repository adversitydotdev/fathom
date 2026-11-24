"""Spec 0.2.x readability and ogrl-library HEAD with RFC 0001 §6.3 mapping IDs."""

import asyncio

from fathom.adapters.library import GitLibrary
from fathom.kernel import bundles
from fathom.kernel.ids import is_reserved, split
from fathom.kernel.models import Requirement, parse, readable_spec_version
from fathom.operations.library import check_library
from tests.conftest import STAMP

FATHOM_LIBRARY = "https://github.com/adversitydotdev/ogrl-library"


def test_readable_spec_version_accepts_0_1_and_0_2_patches():
    assert readable_spec_version("0.1.0")
    assert readable_spec_version("0.1.9")
    assert readable_spec_version("0.2.0")
    assert readable_spec_version("0.2.3")
    assert not readable_spec_version("0.3.0")
    assert not readable_spec_version("1.0.0")


def test_parse_spec_0_2_objects_with_section_6_3_ids():
    req = Requirement.model_validate(
        {
            "type": "requirement",
            "id": "requirement--soc2-tsc-2017-cc6.1",
            "spec_version": "0.2.0",
            "created": STAMP,
            "modified": STAMP,
            "name": "Logical access",
            "framework_ref": "framework--soc2-tsc-2017",
            "class": "criterion",
        }
    )
    assert req.spec_version == "0.2.0"
    mapping = parse(
        {
            "type": "mapping",
            "id": "mapping--ogrl-ac-01_to_soc2-tsc-2017-cc6.1",
            "spec_version": "0.2.1",
            "created": STAMP,
            "modified": STAMP,
            "source_ref": "control--ogrl-ac-01",
            "target_ref": "requirement--soc2-tsc-2017-cc6.1",
            "relationship": "equal-to",
        }
    )
    assert mapping.spec_version == "0.2.1"
    _, remainder = split(mapping.id)
    assert "_to_" in remainder
    assert is_reserved(mapping.id)


def test_fathom_library_main_passes_kernel_and_fathom_rs_checks():
    """ogrl-library main after the §6.3 ID rename (spec 0.2.0); needs network."""

    async def pull() -> list:
        lib = GitLibrary(FATHOM_LIBRARY)
        revision = await lib.checkout(None, "HEAD")
        _, objects = bundles.read_directory(revision.root)
        check_library(objects)
        return objects

    objects = asyncio.run(pull())
    assert any(o.spec_version.startswith("0.2.") for o in objects)
    ids = {o.id for o in objects if o.type == "mapping"}
    assert any("_to_" in oid for oid in ids)
    assert not any("-to-" in oid for oid in ids)
