"""Objects on disk and on the wire, RFC 0001 sections 6.1 and 6.5.

Reading a repository-form bundle walks `{type}/**.yaml` beside the manifest.
Reading an exchange-form bundle takes `objects` from the manifest. Writing
uses one object per file at `{type}/{remainder}.yaml` in canonical field
order, so a commit is a change in objects and not a reorder of keys.
"""

import hashlib
import json
from collections.abc import Iterable
from datetime import date, datetime
from pathlib import Path
from typing import Any

import yaml

from opengrc.kernel import ids
from opengrc.kernel.models import Envelope, parse, readable_spec_version
from opengrc.kernel.timeutil import format_timestamp

try:  # the C loader is much faster on the 1,700-file NIST tree
    from yaml import CSafeDumper as SafeDumper
    from yaml import CSafeLoader as SafeLoader
except ImportError:  # pragma: no cover
    from yaml import SafeDumper, SafeLoader  # type: ignore[assignment]

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
    return json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def projection_digest(objects: Iterable[Envelope]) -> str:
    """A stable hash of a set of objects, independent of file layout."""
    bodies = sorted((o.body() for o in objects), key=lambda b: b["id"])
    return "sha-256:" + digest(canonical_json(bodies))


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


def read_exchange(content: str | bytes) -> tuple[dict[str, Any], list[Envelope]]:
    """An exchange-form bundle: the manifest with every object inlined."""
    try:
        manifest = read_manifest(load_text(content))
    except yaml.YAMLError as exc:
        raise BundleError(f"the bundle is not YAML or JSON: {exc}") from exc
    raw = manifest.get("objects")
    if not isinstance(raw, list):
        raise BundleError("an exchange bundle lists its objects in `objects`")
    return manifest, [parse_object(o, f"objects[{i}]") for i, o in enumerate(raw)]


def read_directory(root: Path, manifest_name: str = "bundle.yaml") -> tuple[dict, list[Envelope]]:
    """A repository-form bundle: a manifest and one object per sibling file."""
    manifest_path = root / manifest_name
    if not manifest_path.is_file():
        raise BundleError(f"{manifest_path} is missing")
    manifest = read_manifest(load_text(manifest_path.read_bytes()))
    objects: list[Envelope] = []
    for path in sorted(root.rglob("*.yaml")):
        if path == manifest_path or path.name.startswith("."):
            continue
        objects.append(parse_object(load_text(path.read_bytes()), str(path.relative_to(root))))
    return manifest, objects


def _ordered(body: dict[str, Any]) -> dict[str, Any]:
    head = {k: body[k] for k in ENVELOPE_ORDER if k in body}
    tail = {k: body[k] for k in sorted(body) if k not in head}
    return {**head, **tail}


class _Dumper(SafeDumper):
    pass


def _str(dumper: yaml.SafeDumper, value: str) -> yaml.Node:
    style = ">" if len(value) > 80 and "\n" not in value.rstrip("\n") else None
    if "\n" in value.rstrip("\n"):
        style = "|"
    return dumper.represent_scalar("tag:yaml.org,2002:str", value, style=style)


_Dumper.add_representer(str, _str)


def dump_yaml(body: dict[str, Any]) -> str:
    return yaml.dump(
        _ordered(body), Dumper=_Dumper, sort_keys=False, allow_unicode=True, width=78
    )


def object_path(object_id: str) -> str:
    kind, remainder = ids.split(object_id)
    return f"{kind}/{remainder}.yaml"
