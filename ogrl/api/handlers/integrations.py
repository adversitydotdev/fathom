"""Handlers for integrations, connections, and snapshots (RFC 0005)."""

from typing import Annotated

from fastapi import Body, Query, Response

from ogrl.api.handlers.objects import IfMatch
from ogrl.api.paths import integrations as i
from ogrl.api.registrar import CurrentPrincipal, Registrar
from ogrl.container import Container
from ogrl.kernel.rules import SNAPSHOT_MEDIA_TYPE
from ogrl.operations.integrations import (
    CollectionRequest,
    ConnectionPatch,
    ConnectionWrite,
    SecretWrite,
    TemplateEnable,
)


def register(registrar: Registrar, c: Container) -> None:
    s = c.integrations

    async def list_integrations(principal: CurrentPrincipal):
        return {"data": await s.list_integrations(principal)}

    async def get_integration(id: str, principal: CurrentPrincipal):
        return await s.get_integration(principal, id)

    async def enable_template(
        id: str,
        name: str,
        principal: CurrentPrincipal,
        body: Annotated[TemplateEnable | None, Body()] = None,
    ):
        return await s.enable_template(principal, id, name, body or TemplateEnable())

    registrar.handle(i.LIST_INTEGRATIONS, list_integrations)
    registrar.handle(i.GET_INTEGRATION, get_integration)
    registrar.handle(i.ENABLE_TEMPLATE, enable_template)

    async def list_connections(principal: CurrentPrincipal):
        return {"data": await s.list_connections(principal)}

    async def create_connection(body: ConnectionWrite, principal: CurrentPrincipal):
        return await s.create_connection(principal, body)

    async def get_connection(id: str, principal: CurrentPrincipal):
        return await s.get_connection(principal, id)

    async def update_connection(
        id: str, body: ConnectionPatch, if_match: IfMatch, principal: CurrentPrincipal
    ):
        return await s.update_connection(principal, id, body, if_match)

    async def delete_connection(id: str, principal: CurrentPrincipal) -> Response:
        await s.delete_connection(principal, id)
        return Response(status_code=204)

    async def set_secret(id: str, name: str, body: SecretWrite, principal: CurrentPrincipal):
        return await s.put_secret(principal, id, name, body)

    async def validate_connection(id: str, principal: CurrentPrincipal):
        return await s.validate(principal, id)

    async def collect(
        id: str,
        principal: CurrentPrincipal,
        body: Annotated[CollectionRequest | None, Body()] = None,
    ):
        return await s.collect(principal, id, body or CollectionRequest())

    registrar.handle(i.LIST_CONNECTIONS, list_connections)
    registrar.handle(i.CREATE_CONNECTION, create_connection)
    registrar.handle(i.GET_CONNECTION, get_connection)
    registrar.handle(i.UPDATE_CONNECTION, update_connection)
    registrar.handle(i.DELETE_CONNECTION, delete_connection)
    registrar.handle(i.SET_SECRET, set_secret)
    registrar.handle(i.VALIDATE_CONNECTION, validate_connection)
    registrar.handle(i.COLLECT, collect)

    async def list_snapshots(
        principal: CurrentPrincipal,
        connection_id: Annotated[str | None, Query()] = None,
        source: Annotated[str | None, Query()] = None,
    ):
        return {"data": await s.list_snapshots(principal, connection_id, source)}

    async def get_snapshot(id: str, principal: CurrentPrincipal):
        return await s.get_snapshot(principal, id)

    async def get_snapshot_content(id: str, principal: CurrentPrincipal) -> Response:
        content = await s.snapshot_content(principal, id)
        return Response(content, media_type=SNAPSHOT_MEDIA_TYPE)

    registrar.handle(i.LIST_SNAPSHOTS, list_snapshots)
    registrar.handle(i.GET_SNAPSHOT, get_snapshot)
    registrar.handle(i.GET_SNAPSHOT_CONTENT, get_snapshot_content)
