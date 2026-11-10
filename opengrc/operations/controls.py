"""Control use-cases. The API, the CLI, and agent tools all call these.

Every operation checks its own permission, even though the route guard
already did. The guard is a coarse gate; this is the rule. An agent tool
or a job never passes through the route guard.
"""

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Protocol

from pydantic import BaseModel, ConfigDict

from opengrc.access import Authorizer, Permission, Principal, require
from opengrc.errors import Conflict, FieldError, Invalid, NotFound, PreconditionFailed
from opengrc.kernel import ids
from opengrc.kernel.models import Control, ControlType, Frequency, Origin, Parameter
from opengrc.operations.pagination import Page, PageInfo, PageRequest


class ControlWrite(BaseModel):
    """`ControlWrite` in api/openapi.yaml. PATCH merges the fields sent; arrays replace."""

    model_config = ConfigDict(extra="forbid")

    id: str | None = None
    name: str
    statement: str
    objective: str
    display_id: str | None = None
    family: str | None = None
    control_type: ControlType | None = None
    frequency: Frequency | None = None
    summary: str | None = None
    guidance: str | None = None
    parameters: dict[str, Parameter] | None = None
    tags: list[str] | None = None


class ControlQuery(PageRequest):
    origin: Origin | None = None
    family: str | None = None
    q: str | None = None
    revoked: bool = False


class ControlRepository(Protocol):
    """Only what this service needs. Postgres and in-memory both satisfy it."""

    async def get(self, control_id: str) -> Control | None: ...

    async def page(self, query: ControlQuery) -> tuple[list[Control], str | None]: ...

    async def insert(self, control: Control) -> None:
        """Raises Conflict when the id is taken."""
        ...

    async def replace(self, control: Control, expected_modified: datetime) -> None:
        """Atomic compare-and-set on `modified`. Raises PreconditionFailed when stale."""
        ...


def utcnow() -> datetime:
    return datetime.now(UTC)


class ControlService:
    def __init__(
        self,
        repository: ControlRepository,
        authorizer: Authorizer,
        clock: Callable[[], datetime] = utcnow,
    ) -> None:
        self._repository = repository
        self._authorizer = authorizer
        self._clock = clock

    async def list(self, principal: Principal, query: ControlQuery) -> Page[Control]:
        require(self._authorizer, principal, Permission.CONTROLS_READ)
        controls, next_cursor = await self._repository.page(query)
        info = PageInfo(next_cursor=next_cursor, limit=query.limit)
        return Page[Control](data=controls, page=info)

    async def get(self, principal: Principal, control_id: str) -> Control:
        require(self._authorizer, principal, Permission.CONTROLS_READ)
        return await self._load(control_id)

    async def create(self, principal: Principal, write: ControlWrite) -> Control:
        require(self._authorizer, principal, Permission.CONTROLS_WRITE)
        control_id = write.id or ids.mint("control")
        self._check_custom_id(control_id)
        now = self._clock()
        control = Control(
            **write.model_dump(exclude={"id"}, exclude_none=True),
            id=control_id,
            origin=Origin.CUSTOM,
            created=now,
            modified=now,
            created_by_ref=principal.actor_id,
        )
        await self._repository.insert(control)
        return control

    async def update(
        self, principal: Principal, control_id: str, write: ControlWrite, if_match: datetime
    ) -> Control:
        require(self._authorizer, principal, Permission.CONTROLS_WRITE)
        current = await self._editable(control_id, if_match)
        changes = write.model_dump(exclude={"id"}, exclude_unset=True)
        updated = current.model_copy(update={**changes, "modified": self._clock()})
        # model_copy skips validation; re-validate so a bad merge is a 400, not a stored row.
        updated = Control.model_validate(updated.model_dump())
        await self._repository.replace(updated, expected_modified=if_match)
        return updated

    async def revoke(self, principal: Principal, control_id: str, if_match: datetime) -> Control:
        require(self._authorizer, principal, Permission.CONTROLS_REVOKE)
        current = await self._editable(control_id, if_match)
        revoked = current.model_copy(update={"revoked": True, "modified": self._clock()})
        await self._repository.replace(revoked, expected_modified=if_match)
        return revoked

    async def _load(self, control_id: str) -> Control:
        control = await self._repository.get(control_id)
        if control is None:
            raise NotFound(f"no control {control_id}")
        return control

    async def _editable(self, control_id: str, if_match: datetime) -> Control:
        control = await self._load(control_id)
        if control.read_only:
            raise Conflict("library controls are read-only", slug="library-object")
        if control.modified != if_match:
            raise PreconditionFailed(f"If-Match does not equal modified ({control.modified})")
        return control

    @staticmethod
    def _check_custom_id(control_id: str) -> None:
        try:
            object_type, _ = ids.split(control_id)
            reserved = ids.is_reserved(control_id)
        except ValueError as exc:
            raise Invalid(errors=[FieldError(str(exc), "/id")]) from exc
        if object_type != "control":
            raise Invalid(errors=[FieldError("id must start with control--", "/id")])
        if reserved:
            raise Invalid(
                errors=[FieldError("bare slugs are reserved for the standard library", "/id")]
            )
