"""Control handlers: parse the request, call one operation, shape the response.

No rules live here. `ControlOperations` is declared by this consumer and lists
only what these handlers call; `ControlService` satisfies it structurally.
"""

from datetime import datetime
from typing import Annotated, Protocol

from fastapi import Header, Query, Response

from opengrc.access import Principal
from opengrc.api import paths
from opengrc.api.registrar import CurrentPrincipal, Registrar
from opengrc.kernel.models import Control
from opengrc.operations.controls import ControlQuery, ControlWrite
from opengrc.operations.pagination import Page

IfMatch = Annotated[datetime, Header(alias="If-Match")]


class ControlOperations(Protocol):
    async def list(self, principal: Principal, query: ControlQuery) -> Page[Control]: ...
    async def get(self, principal: Principal, control_id: str) -> Control: ...
    async def create(self, principal: Principal, write: ControlWrite) -> Control: ...
    async def update(
        self, principal: Principal, control_id: str, write: ControlWrite, if_match: datetime
    ) -> Control: ...
    async def revoke(
        self, principal: Principal, control_id: str, if_match: datetime
    ) -> Control: ...


class ControlHandlers:
    def __init__(self, operations: ControlOperations) -> None:
        self._operations = operations

    async def list(
        self, principal: CurrentPrincipal, query: Annotated[ControlQuery, Query()]
    ) -> Page[Control]:
        return await self._operations.list(principal, query)

    async def get(self, id: str, principal: CurrentPrincipal) -> Control:
        return await self._operations.get(principal, id)

    async def create(
        self, body: ControlWrite, principal: CurrentPrincipal, response: Response
    ) -> Control:
        control = await self._operations.create(principal, body)
        response.headers["Location"] = paths.controls.GET_CONTROL.url(id=control.id)
        return control

    async def update(
        self, id: str, body: ControlWrite, if_match: IfMatch, principal: CurrentPrincipal
    ) -> Control:
        return await self._operations.update(principal, id, body, if_match)

    async def revoke(self, id: str, if_match: IfMatch, principal: CurrentPrincipal) -> Control:
        return await self._operations.revoke(principal, id, if_match)


def register(registrar: Registrar, operations: ControlOperations) -> None:
    handlers = ControlHandlers(operations)
    registrar.handle(paths.controls.LIST_CONTROLS, handlers.list)
    registrar.handle(paths.controls.CREATE_CONTROL, handlers.create)
    registrar.handle(paths.controls.GET_CONTROL, handlers.get)
    registrar.handle(paths.controls.UPDATE_CONTROL, handlers.update)
    registrar.handle(paths.controls.REVOKE_CONTROL, handlers.revoke)
