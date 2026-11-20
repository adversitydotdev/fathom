"""Objects on disk and on the wire, RFC 0001 sections 6.1 and 6.5.

Backed by `ogrl_rs` (Rust `ogrl-core`) for parallel directory loading,
strict/canonical YAML 1.2 formatting, and RFC 8785 SHA-256 projection digests,
while hydrating Pydantic `Envelope` models for the Python application layer.
"""

import hashlib
from collections.abc import Iterable
from datetime import date, datetime
from pathlib import Path
from typing import Any

import ogrl_rs
import yaml

from ogrl.kernel import ids
from ogrl.kernel.models import Envelope, parse, readable_spec_version
from ogrl.kernel.timeutil import format_timestamp

try:  # fallback loader for non-bundle YAML fragments
    from yaml import CSafeLoader as SafeLoader
except ImportError:  # pragma: no cover
    from yaml import SafeLoader  # type: ignore[assignment]

ENVELOPE_ORDER = (
    "type",
    "id",
    "spec_version",
    "created",
    "modified",
    "name",
    "display_id",
    "revoked",
    "created_by_ref",
)


class BundleError(ValueError):
    """A bundle or one of its objects cannot be read. `object_id` names it when known."""

    def __init__(self, detail: str, object_id: str | None = None) -> None:
        super().__init__(detail)
        self.object_id = object_id


def _jsonable(value: Any) -> Any:
    """YAML 1.1 loaders turn unquoted timestamps and dates into Python values."""
    if isinstance(value, datetime):
        return format_timestamp(value)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_jsonable(v) for v in value]
    return value


def load_text(text: str | bytes) -> Any:
    return _jsonable(yaml.load(text, Loader=SafeLoader))  # noqa: S506 - SafeLoader


def canonical_json(body: Any) -> bytes:
    """RFC 8785 for the values this language uses: sorted keys, no whitespace."""
    return ogrl_rs.canonical_json(body)


def digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def projection_digest(objects: Iterable[Envelope]) -> str:
    """A stable hash of a set of objects, independent of file layout."""
    bodies = [o.body() for o in objects]
    return ogrl_rs.projection_digest(bodies)


def parse_object(body: Any, where: str = "") -> Envelope:
    if not isinstance(body, dict):
        raise BundleError(f"{where or 'object'} is not a mapping")
    object_id = body.get("id") if isinstance(body.get("id"), str) else None
    try:
        obj = parse(body)
        kind, _ = ids.split(obj.id)
    except Exception as exc:  # pydantic.ValidationError, ValueError
        raise BundleError(f"{object_id or where}: {exc}", object_id) from exc
    if kind != obj.type:
        raise BundleError(f"{obj.id}: the id's type is not {obj.type}", obj.id)
    return obj


def read_manifest(body: Any) -> dict[str, Any]:
    if not isinstance(body, dict) or body.get("type") != "bundle":
        raise BundleError("the manifest is not a bundle")
    version = str(body.get("spec_version", ""))
    if not readable_spec_version(version):
        raise BundleError(f"spec_version {version!r} is not one this reader accepts")
    return body


def _raise_first_diagnostic(diagnostics: list[dict[str, Any]]) -> None:
    if diagnostics:
        first = diagnostics[0]
        object_id = first.get("object_id")
        detail = first.get("detail") or "invalid object"
        raise BundleError(f"{object_id}: {detail}" if object_id else detail, object_id)


def read_exchange(content: str | bytes) -> tuple[dict[str, Any], list[Envelope]]:
    """An exchange-form bundle: the manifest with every object inlined."""
    try:
        loaded = ogrl_rs.read_exchange(content, strict=False)
    except ValueError as exc:
        raise BundleError(str(exc)) from exc
    _raise_first_diagnostic(loaded.get("diagnostics", []))
    manifest = loaded["manifest"]
    objects = [parse_object(o, f"objects[{i}]") for i, o in enumerate(loaded.get("objects", []))]
    return manifest, objects


def read_directory(root: Path, manifest_name: str = "bundle.yaml") -> tuple[dict, list[Envelope]]:
    """A repository-form bundle: a manifest and one object per sibling file."""
    manifest_path = root / manifest_name
    if not manifest_path.is_file():
        raise BundleError(f"{manifest_path} is missing")
    if manifest_name == "bundle.yaml":
        try:
            loaded = ogrl_rs.read_directory(root, strict=False)
        except ValueError as exc:
            raise BundleError(str(exc)) from exc
        _raise_first_diagnostic(loaded.get("diagnostics", []))
        objects = [parse_object(o) for o in loaded.get("objects", [])]
        return loaded["manifest"], objects

    manifest = read_manifest(load_text(manifest_path.read_bytes()))
    objects = []
    for path in sorted(root.rglob("*.yaml")):
        if path == manifest_path or path.name.startswith("."):
            continue
        objects.append(parse_object(load_text(path.read_bytes()), str(path.relative_to(root))))
    return manifest, objects


def dump_yaml(body: dict[str, Any]) -> str:
    return ogrl_rs.format_yaml(body)


def object_path(object_id: str) -> str:
    kind, remainder = ids.split(object_id)
    return f"{kind}/{remainder}.yaml"
