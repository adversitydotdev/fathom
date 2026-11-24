"""Integration packages and their manifests, RFC 0005 section 3.

A package is a directory (an unpacked archive) holding `manifest.yaml`, one
JSON Schema per resource, and code for one runtime. Loading validates the
manifest and every schema; nothing here runs the package.
"""

import hashlib
import json
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, Literal

import yaml
from jsonschema import Draft202012Validator
from ogrl_integration import openapi, smithy
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

from fathom.integrations.apimodel import ApiModel, OpenApiModel, SmithyModel
from fathom.kernel import rules

PROTOCOL_VERSION = 1
NAME = re.compile(r"^[a-z0-9-]+$")
ENV_NAME = re.compile(r"^[A-Z][A-Z0-9_]*$")
INTEGRATION_ID = re.compile(r"^[a-z0-9-]+(?:\.[a-z0-9-]+)+$")
SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?$")
RESERVED_ENV = frozenset({"PATH", "HOME", "LANG", "PYTHONPATH"})


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class Runtime(_Model):
    kind: Literal["python", "binary"]
    entrypoint: str  # python: `module:function`; binary: executable name under bin/<platform>/

    @field_validator("entrypoint")
    @classmethod
    def _entrypoint(cls, value: str) -> str:
        if ".." in value or value.startswith("/"):
            raise ValueError("entrypoint is a module path or a bare executable name")
        return value


class ConfigField(_Model):
    name: str
    label: str
    pattern: str | None = None
    required: bool = True

    @field_validator("pattern")
    @classmethod
    def _pattern(cls, value: str | None) -> str | None:
        if value is not None:
            re.compile(value)
        return value


class SecretField(_Model):
    name: str
    label: str
    secret: bool = True

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        if not ENV_NAME.match(value) or value in RESERVED_ENV or value.startswith("OGRL_"):
            raise ValueError("an upper-case environment variable name not reserved by OGRL")
        return value


class FieldsAuth(_Model):
    kind: Literal["fields"]
    label: str
    fields: list[SecretField] = Field(min_length=1)


class OAuth2Auth(_Model):
    kind: Literal["oauth2"]
    label: str
    authorize_url: str
    token_url: str
    scopes: list[str] = Field(default_factory=list)
    pkce: bool = True


class AwsRoleAuth(_Model):
    kind: Literal["aws_role"]
    label: str


Auth = FieldsAuth | OAuth2Auth | AwsRoleAuth


class ResourceSpec(_Model):
    name: str
    version: int = Field(ge=1)
    schema_path: str = Field(alias="schema")

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        if not NAME.match(value):
            raise ValueError("resource names match [a-z0-9-]+")
        return value


class CheckSpec(_Model):
    name: str
    version: int = Field(ge=1)
    sources: list[str] = Field(min_length=1)  # resource names in this integration
    args: dict[str, Any] = Field(default_factory=dict)

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        if not NAME.match(value):
            raise ValueError("check names match [a-z0-9-]+")
        return value


class OpenApiBlock(_Model):
    """Query source support (RFC 0006 section 4)."""

    description: str
    base_url: str
    pagination: str = "link"
    read_operations: list[str] = Field(default_factory=list)
    authorization: str = ""

    @field_validator("pagination")
    @classmethod
    def _pagination(cls, value: str) -> str:
        kind = value.split(":", 1)[0]
        if kind not in ("link", "next-url", "cursor", "none"):
            raise ValueError("link, next-url:<path>, cursor:<path>:<param>, or none")
        return value


SERVICE_NAME = re.compile(r"^[a-z0-9]+$")


class SmithyService(_Model):
    """One AWS service a package bundles a Smithy model for (RFC 0007 section 2)."""

    model: str
    endpoint: str
    signing_region: str = "us-east-1"
    target_prefix: str = ""

    @field_validator("endpoint")
    @classmethod
    def _endpoint(cls, value: str) -> str:
        loopback = value.startswith(("http://127.0.0.1:", "http://localhost:"))  # emulators
        if not value.startswith("https://") and not loopback:
            raise ValueError("an https:// URL")
        if set(re.findall(r"\{(\w+)\}", value)) - {"region"}:
            raise ValueError("the only placeholder is {region}")
        return value


class SmithyBlock(_Model):
    """Query source support over AWS Smithy models (RFC 0007 section 2)."""

    services: dict[str, SmithyService] = Field(min_length=1)
    read_operations: list[str] = Field(default_factory=list)
    deny_operations: list[str] = Field(default_factory=list)

    @field_validator("services")
    @classmethod
    def _services(cls, value: dict[str, SmithyService]) -> dict[str, SmithyService]:
        for name in value:
            if not SERVICE_NAME.match(name):
                raise ValueError(f"service names match [a-z0-9]+, not {name!r}")
        return value


class Template(_Model):
    name: str
    fulfills_ref: str | None = None
    test: dict[str, Any]


class Manifest(_Model):
    id: str
    name: str
    version: str
    protocol: int
    publisher: str
    description: str | None = None
    runtime: Runtime
    egress: list[str] = Field(default_factory=list)
    config: list[ConfigField] = Field(default_factory=list)
    auth: list[Auth] = Field(min_length=1)
    resources: list[ResourceSpec] = Field(min_length=1)
    checks: list[CheckSpec] = Field(default_factory=list)
    templates: list[Template] = Field(default_factory=list)
    openapi: OpenApiBlock | None = None
    smithy: SmithyBlock | None = None

    @model_validator(mode="after")
    def _one_api_model(self) -> "Manifest":
        if self.openapi is not None and self.smithy is not None:
            raise ValueError("declare openapi or smithy, not both")
        return self

    @property
    def queryable(self) -> bool:
        """Whether query sources can be defined over this integration (RFC 0006, 0007)."""
        return self.openapi is not None or self.smithy is not None

    @field_validator("id")
    @classmethod
    def _id(cls, value: str) -> str:
        if not INTEGRATION_ID.match(value):
            raise ValueError("a reverse domain name, such as dev.adversity.okta")
        return value

    @field_validator("version")
    @classmethod
    def _version(cls, value: str) -> str:
        if not SEMVER.match(value):
            raise ValueError("a semantic version, such as 1.4.0")
        return value

    @field_validator("protocol")
    @classmethod
    def _protocol(cls, value: int) -> int:
        if value != PROTOCOL_VERSION:
            raise ValueError(f"this server speaks protocol {PROTOCOL_VERSION}")
        return value

    def resource(self, name: str, version: int) -> ResourceSpec | None:
        return next((r for r in self.resources if r.name == name and r.version == version), None)

    def check(self, name: str, version: int) -> CheckSpec | None:
        return next((c for c in self.checks if c.name == name and c.version == version), None)

    def auth_kind(self, kind: str) -> Auth | None:
        return next((a for a in self.auth if a.kind == kind), None)

    def template(self, name: str) -> Template | None:
        return next((t for t in self.templates if t.name == name), None)


class PackageError(ValueError):
    pass


Tier = Literal["first-party", "verified", "local"]


@dataclass(frozen=True)
class Package:
    """An installed, validated package.

    A directory package (`FATHOM_INTEGRATIONS_DIR`) has a `root` on disk, which
    may be read-only. An archive package has no root: its `files` are held in
    memory and the host runs it from there, so nothing is unpacked to disk.
    """

    manifest: Manifest
    root: Path | None
    digest: str  # sha-256 of manifest.yaml for directories; of the archive for installs
    tier: Tier = "local"
    schemas: dict[tuple[str, int], dict[str, Any]] = field(default_factory=dict)
    files: Mapping[str, bytes] = field(default_factory=dict)

    @property
    def id(self) -> str:
        return self.manifest.id

    def schema(self, name: str, version: int) -> dict[str, Any]:
        return self.schemas[(name, version)]

    def read(self, relative: str) -> bytes:
        """A file of the package, from memory or from its directory."""
        path = PurePosixPath(relative)
        if ".." in path.parts or path.is_absolute():
            raise PackageError(f"{relative} is outside the package")
        if self.root is None:
            raw = self.files.get(str(path))
            if raw is None:
                raise PackageError(f"the package has no {relative}")
            return raw
        try:
            return (self.root / relative).read_bytes()
        except OSError as exc:
            raise PackageError(f"the package has no readable {relative}") from exc

    def api_model(self) -> ApiModel | None:
        """The bundled API model query sources are defined over, loaded once per version."""
        manifest = self.manifest
        if not manifest.queryable:
            return None
        key = (manifest.id, self.digest)
        if key not in _API_MODELS:
            try:
                if manifest.smithy is not None:
                    settings = smithy.Settings.from_json(manifest.smithy.model_dump())
                    _API_MODELS[key] = SmithyModel(smithy.load(settings, self.read))
                else:
                    block = manifest.openapi
                    assert block is not None
                    text = self.read(block.description).decode()
                    document = (
                        json.loads(text)
                        if block.description.endswith(".json")
                        else yaml.safe_load(text)
                    )
                    settings_ = openapi.Settings.from_json(block.model_dump())
                    _API_MODELS[key] = OpenApiModel(settings_, openapi.Description(document))
            except PackageError:
                raise
            except (ValueError, KeyError) as exc:
                raise PackageError(f"{manifest.id} {manifest.version}: {exc}") from exc
        return _API_MODELS[key]


_API_MODELS: dict[tuple[str, str], ApiModel] = {}


def _unique(values: list[Any], what: str) -> None:
    if len(set(values)) != len(values):
        raise PackageError(f"each {what} is listed once")


def load_package(root: Path, tier: Tier = "local") -> Package:
    """A package from a directory on disk."""

    def read(relative: str) -> bytes:
        path = (root / relative).resolve()
        if root.resolve() not in path.parents:
            raise PackageError(f"{relative} is outside the package")
        try:
            return path.read_bytes()
        except OSError as exc:
            raise PackageError(f"{root}: no readable {relative}") from exc

    package = _load(read, tier, where=str(root))
    return Package(package.manifest, root, package.digest, tier, package.schemas)


def load_files(files: Mapping[str, bytes], tier: Tier = "local") -> Package:
    """A package from an archive already read into memory."""

    def read(relative: str) -> bytes:
        try:
            return files[str(PurePosixPath(relative))]
        except KeyError as exc:
            raise PackageError(f"the archive has no {relative}") from exc

    package = _load(read, tier, where="archive")
    return Package(package.manifest, None, package.digest, tier, package.schemas, dict(files))


def _load(read: Callable[[str], bytes], tier: Tier, where: str) -> Package:
    raw = read("manifest.yaml")
    try:
        manifest = Manifest.model_validate(yaml.safe_load(raw))
    except ValidationError as exc:
        raise PackageError(f"{where}/manifest.yaml: {exc}") from exc
    except yaml.YAMLError as exc:
        raise PackageError(f"{where}/manifest.yaml is not YAML: {exc}") from exc

    _unique([(r.name, r.version) for r in manifest.resources], "resource version")
    _unique([(c.name, c.version) for c in manifest.checks], "check version")
    _unique([t.name for t in manifest.templates], "template")
    _unique([a.kind for a in manifest.auth], "auth kind")

    schemas: dict[tuple[str, int], dict[str, Any]] = {}
    for resource in manifest.resources:
        schema_path = PurePosixPath(resource.schema_path)
        if ".." in schema_path.parts or schema_path.is_absolute():
            raise PackageError(f"{resource.name}: the schema is outside the package")
        try:
            schema = yaml.safe_load(read(resource.schema_path))
            Draft202012Validator.check_schema(schema)
        except PackageError:
            raise
        except Exception as exc:
            raise PackageError(f"{resource.name}: {resource.schema_path}: {exc}") from exc
        if schema.get("type") != "object":
            raise PackageError(f"{resource.name}: an item schema has type object")
        schemas[(resource.name, resource.version)] = schema

    names = {r.name for r in manifest.resources}
    for check in manifest.checks:
        missing = sorted(set(check.sources) - names)
        if missing:
            raise PackageError(f"check {check.name} reads unknown resources {', '.join(missing)}")
    for template in manifest.templates:
        run = template.test.get("run") or {}
        for text in [run.get("source"), run.get("check"), *(run.get("sources") or [])]:
            if text is None:
                continue
            try:
                ref = rules.parse_reference(text)
            except ValueError as exc:
                raise PackageError(f"template {template.name}: {exc}") from exc
            if ref.integration != manifest.id:
                raise PackageError(f"template {template.name} reads another integration: {text}")

    return Package(manifest, None, hashlib.sha256(raw).hexdigest(), tier, schemas)


def discover(directory: Path) -> list[Package]:
    """Every package directly under `directory`, as `<anything>/manifest.yaml`."""
    if not directory.is_dir():
        return []
    return [
        load_package(child)
        for child in sorted(directory.iterdir())
        if (child / "manifest.yaml").is_file()
    ]
