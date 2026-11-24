"""Create, read, update, and revoke for every object type.

The rules every collection shares live here (RFC 0004 section 3):

- The server sets `created`, `modified`, `spec_version`, and `created_by_ref`.
- A client id is a UUID or a domain slug of the right type. The library's
  slug space is refused.
- `PATCH` is JSON Merge Patch (RFC 7386): the fields sent are merged, `null`
  removes a field, arrays replace.
- `If-Match` equals `modified`, and the check is the store's compare-and-set.
- Library and provider rows are read-only. There is no delete; revoke.
- Unknown fields are stored and returned.

What differs per type is a `TypeSpec`: the models, the permissions, what the
server fills in, and which writes an agent may not make (RFC 0003 section 4).
Graph constraints come from the kernel.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ValidationError

from fathom.access import ActorKind, Authorizer, Permission, Principal, require
from fathom.errors import Conflict, FieldError, Forbidden, Invalid, NotFound, PreconditionFailed
from fathom.kernel import constraints, ids
from fathom.kernel.graph import Graph
from fathom.kernel.models import SPEC_VERSION, Envelope
from fathom.kernel.timeutil import later_than, now, utc
from fathom.operations.pagination import Page, PageInfo, PageRequest, decode_cursor, encode_cursor
from fathom.operations.records import LIBRARY, ORGANIZATION
from fathom.operations.store import ObjectStore, Row

SERVER_FIELDS = ("type", "spec_version", "created", "modified", "revoked", "created_by_ref")


@dataclass
class WriteContext:
    """What a type's hooks may read while a write is prepared."""

    principal: Principal
    store: ObjectStore
    graph: Graph
    old: Envelope | None
    patch: dict[str, Any] | None = None  # the fields a PATCH sent, before the merge


# prepare(body, ctx) -> body: fill or refuse server-owned fields.
Prepare = Callable[[dict[str, Any], WriteContext], Awaitable[dict[str, Any]]]
# extra(new, old) -> permissions the write needs beyond the type's write permission.
Extra = Callable[[Envelope, Envelope | None], list[Permission]]
# gate(new, old) -> why an agent may not make this write, or None.
Gate = Callable[[Envelope, Envelope | None], str | None]
Matches = Callable[[Row, Any], bool]


async def _keep(body: dict[str, Any], _: WriteContext) -> dict[str, Any]:
    return body


@dataclass(frozen=True)
class TypeSpec:
    type: str
    model: type[Envelope]
    query: type[PageRequest] = PageRequest
    write: type[BaseModel] | None = None
    read_permission: Permission = Permission.PROGRAMS_READ
    write_permission: Permission | None = None
    revoke_permission: Permission | None = Permission.OBJECTS_REVOKE
    matches: Matches = lambda row, query: True  # noqa: E731
    prepare: Prepare = _keep
    extra_permissions: Extra = lambda new, old: []  # noqa: E731
    agent_gate: Gate = lambda new, old: None  # noqa: E731
    agent_may_create: bool = True
    noun: str = ""
    hidden_by_default: Callable[[Row], bool] = field(default=lambda row: row.obj.is_revoked)

    @property
    def label(self) -> str:
        return self.noun or self.type.replace("_", " ")


def merge_patch(target: Any, patch: Any) -> Any:
    """RFC 7386."""
    if not isinstance(patch, dict):
        return patch
    result = dict(target) if isinstance(target, dict) else {}
    for key, value in patch.items():
        if value is None:
            result.pop(key, None)
        else:
            result[key] = merge_patch(result.get(key), value)
    return result


def field_errors(exc: ValidationError) -> list[FieldError]:
    out = []
    for error in exc.errors():
        loc = [str(part) for part in error["loc"] if not str(part).startswith("function-")]
        out.append(FieldError(error["msg"], "/" + "/".join(loc) if loc else None))
    return out


def violations_to_error(violations: list[constraints.Violation]) -> Exception:
    conflicts = [v for v in violations if v.conflict]
    if conflicts:
        return Conflict(conflicts[0].detail, slug="duplicate")
    return Invalid(
        "the object violates a graph constraint",
        errors=[FieldError(v.detail, v.pointer) for v in violations],
    )


def read_only_error(row: Row, label: str) -> Conflict:
    if row.source == LIBRARY:
        return Conflict(f"library {label} rows are read-only here", slug="library-object")
    return Conflict(f"{label} rows imported from a provider are read-only", slug="provider-object")


class ObjectService:
    def __init__(
        self,
        store: ObjectStore,
        authorizer: Authorizer,
        clock: Callable[[], datetime] = now,
    ) -> None:
        self.store = store
        self._authorizer = authorizer
        self._clock = clock

    # --- reads -------------------------------------------------------------------------

    async def load(self, spec: TypeSpec, object_id: str) -> Row:
        row = await self.store.get(object_id)
        if row is None or row.obj.type != spec.type:
            raise NotFound(f"no {spec.label} {object_id}")
        return row

    async def get(self, principal: Principal, spec: TypeSpec, object_id: str) -> Envelope:
        require(self._authorizer, principal, spec.read_permission)
        return (await self.load(spec, object_id)).obj

    async def list(
        self,
        principal: Principal,
        spec: TypeSpec,
        query: PageRequest,
        scope: Callable[[Row], bool] | None = None,
    ) -> Page:
        require(self._authorizer, principal, spec.read_permission)
        include_revoked = bool(getattr(query, "revoked", False))
        after = decode_cursor(query.cursor)
        rows = [
            row
            for row in await self.store.scan(spec.type)
            if (include_revoked or not spec.hidden_by_default(row))
            and (scope is None or scope(row))
            and spec.matches(row, query)
            and (after is None or row.obj.id > after)
        ]
        page = rows[: query.limit]
        more = len(rows) > query.limit
        return Page(
            data=[row.obj for row in page],
            page=PageInfo(
                next_cursor=encode_cursor(page[-1].obj.id) if more else None, limit=query.limit
            ),
        )

    # --- writes ------------------------------------------------------------------------

    def _check_permissions(
        self, principal: Principal, spec: TypeSpec, new: Envelope, old: Envelope | None
    ) -> None:
        if principal.kind is ActorKind.AGENT:
            if old is None and not spec.agent_may_create:
                raise Forbidden(f"an agent does not write a {spec.label}", slug="agent-refused")
            reason = spec.agent_gate(new, old)
            if reason:
                raise Forbidden(reason, slug="agent-refused")
        for permission in spec.extra_permissions(new, old):
            require(self._authorizer, principal, permission)

    def _validate_write(self, spec: TypeSpec, body: dict[str, Any]) -> None:
        if spec.write is None:
            raise Invalid(f"{spec.label} objects are not written here")
        try:
            spec.write.model_validate(body)
        except ValidationError as exc:
            raise Invalid("the body violates the schema", errors=field_errors(exc)) from exc

    def _validate_object(self, spec: TypeSpec, body: dict[str, Any]) -> Envelope:
        try:
            return spec.model.model_validate(body)
        except ValidationError as exc:
            raise Invalid("the object violates the schema", errors=field_errors(exc)) from exc

    @staticmethod
    def check_new_id(spec: TypeSpec, object_id: Any) -> str:
        if not isinstance(object_id, str):
            raise Invalid(errors=[FieldError("id is a string", "/id")])
        try:
            kind, _ = ids.split(object_id)
        except ValueError as exc:
            raise Invalid(errors=[FieldError(str(exc), "/id")]) from exc
        if kind != spec.type:
            raise Invalid(errors=[FieldError(f"id must start with {spec.type}--", "/id")])
        if ids.is_reserved(object_id):
            raise Invalid(
                errors=[FieldError("bare slugs are reserved for the standard library", "/id")]
            )
        return object_id

    async def _constraints(self, obj: Envelope, graph: Graph) -> None:
        violations = constraints.check(obj, graph, ORGANIZATION)
        if violations:
            raise violations_to_error(violations)

    async def create(self, principal: Principal, spec: TypeSpec, body: dict[str, Any]) -> Envelope:
        if spec.write_permission is None:
            raise Invalid(f"{spec.label} objects are not created here")
        require(self._authorizer, principal, spec.write_permission)
        body = {k: v for k, v in body.items() if v is not None and k not in SERVER_FIELDS}
        self._validate_write(spec, body)
        object_id = self.check_new_id(spec, body.get("id", ids.mint(spec.type)))
        if await self.store.get(object_id) is not None:
            raise Conflict(f"id {object_id} is in use", slug="id-taken")
        graph = await self.store.graph()
        body = await spec.prepare(body, WriteContext(principal, self.store, graph, None))
        stamp = utc(self._clock())
        obj = self._validate_object(
            spec,
            {
                **body,
                "type": spec.type,
                "id": object_id,
                "spec_version": SPEC_VERSION,
                "created": stamp,
                "modified": stamp,
                "created_by_ref": principal.actor_id,
            },
        )
        self._check_permissions(principal, spec, obj, None)
        await self._constraints(obj, graph)
        await self.store.insert(Row(obj, ORGANIZATION), principal.actor_id)
        return obj

    async def editable(self, spec: TypeSpec, object_id: str, if_match: datetime) -> Row:
        row = await self.load(spec, object_id)
        if not row.editable:
            raise read_only_error(row, spec.label)
        if row.obj.modified != utc(if_match):
            raise PreconditionFailed(
                f"If-Match does not equal modified ({row.obj.modified.isoformat()})"
            )
        return row

    async def update(
        self,
        principal: Principal,
        spec: TypeSpec,
        object_id: str,
        patch: dict[str, Any],
        if_match: datetime,
    ) -> Envelope:
        if spec.write_permission is None:
            raise Invalid(f"{spec.label} objects are not edited here")
        require(self._authorizer, principal, spec.write_permission)
        row = await self.editable(spec, object_id, if_match)
        old = row.obj
        if "id" in patch and patch["id"] != object_id:
            raise Invalid(errors=[FieldError("id cannot change", "/id")])
        patch = {k: v for k, v in patch.items() if k not in SERVER_FIELDS}
        merged = merge_patch(old.body(), patch)
        writable = {k: v for k, v in merged.items() if k not in SERVER_FIELDS}
        self._validate_write(spec, writable)
        graph = await self.store.graph()
        writable = await spec.prepare(
            writable, WriteContext(principal, self.store, graph, old, patch)
        )
        obj = self._validate_object(
            spec,
            {
                **writable,
                "type": spec.type,
                "id": object_id,
                "spec_version": old.spec_version,
                "created": old.created,
                "modified": later_than(old.modified, self._clock()),
                "created_by_ref": old.created_by_ref,
                "revoked": old.revoked,
            },
        )
        self._check_permissions(principal, spec, obj, old)
        await self._constraints(obj, graph)
        await self.store.replace(obj, expected_modified=old.modified, writer=principal.actor_id)
        return obj

    async def revoke(
        self, principal: Principal, spec: TypeSpec, object_id: str, if_match: datetime
    ) -> Envelope:
        if spec.revoke_permission is None:
            raise Invalid(f"{spec.label} objects are not revoked here")
        require(self._authorizer, principal, spec.revoke_permission)
        if principal.kind is ActorKind.AGENT:
            raise Forbidden("an agent does not revoke; a person does", slug="agent-refused")
        row = await self.editable(spec, object_id, if_match)
        if row.obj.is_revoked:
            return row.obj
        obj = row.obj.model_copy(
            update={"revoked": True, "modified": later_than(row.obj.modified, self._clock())}
        )
        await self.store.replace(obj, expected_modified=row.obj.modified, writer=principal.actor_id)
        return obj

    async def store_as(self, obj: Envelope, writer: str) -> Envelope:
        """Store an object a job produced (a harness result, its evidence), with the same checks."""
        await self._constraints(obj, await self.store.graph())
        await self.store.insert(Row(obj, ORGANIZATION), writer)
        return obj

    async def replace_as(self, obj: Envelope, old: Envelope, writer: str) -> Envelope:
        """Replace an object on behalf of an operation that already checked permission."""
        await self._constraints(obj, await self.store.graph())
        await self.store.replace(obj, expected_modified=old.modified, writer=writer)
        return obj
