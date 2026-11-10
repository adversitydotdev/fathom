"""The organization snapshot written to git (RFC 0002 section 8).

`snapshot(...)` returns the files the export job owns, path to bytes:

- `bundle.yaml`: the manifest, pinning the library and each provider bundle.
- `{type}/{remainder}.yaml`: one file per organization object.
- `{type}/{remainder}.body`: the body of a policy or procedure, beside it.
- `provider/{bundle remainder}/{type}/{remainder}.yaml`: each provider projection.

Library bodies are not copied; they stay in the library repository. Evidence
bytes are not committed; the evidence object carries the URI and the digest.
"""

from collections.abc import Iterable
from datetime import datetime
from typing import Any

from opengrc.kernel import ids
from opengrc.kernel.bundles import dump_yaml, object_path
from opengrc.kernel.models import SPEC_VERSION, Envelope
from opengrc.kernel.timeutil import format_timestamp

OWNED_TOP_LEVEL = frozenset(
    {
        "bundle.yaml",
        "party",
        "component",
        "system",
        "baseline",
        "program",
        "implementation",
        "policy",
        "procedure",
        "evidence",
        "result",
        "finding",
        "risk",
        "exception",
        "control",
        "test",
        "mapping",
        "mapping_review",
        "provider",
    }
)
BODY_SUFFIX = ".body"


def manifest(
    organization_id: str,
    name: str,
    at: datetime,
    library: dict[str, Any] | None,
    providers: list[dict[str, Any]],
) -> dict[str, Any]:
    stamp = format_timestamp(at)
    body: dict[str, Any] = {
        "type": "bundle",
        "id": organization_id,
        "spec_version": SPEC_VERSION,
        "created": stamp,
        "modified": stamp,
        "name": name,
        "version": stamp,
    }
    if library:
        body["library"] = library
    if providers:
        body["providers"] = providers
    return body


def snapshot(
    manifest_body: dict[str, Any],
    organization: Iterable[Envelope],
    providers: dict[str, Iterable[Envelope]],
    bodies: dict[str, bytes],
) -> dict[str, bytes]:
    files: dict[str, bytes] = {"bundle.yaml": dump_yaml(manifest_body).encode()}
    for obj in organization:
        path = object_path(obj.id)
        files[path] = dump_yaml(obj.body()).encode()
        if obj.id in bodies:
            files[path.removesuffix(".yaml") + BODY_SUFFIX] = bodies[obj.id]
    for bundle_id, objects in providers.items():
        _, remainder = ids.split(bundle_id)
        for obj in objects:
            files[f"provider/{remainder}/{object_path(obj.id)}"] = dump_yaml(obj.body()).encode()
    return files
