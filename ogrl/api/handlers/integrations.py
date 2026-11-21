"""Handlers for integrations, connections, and snapshots (RFC 0005)."""

import html
from typing import Annotated

from fastapi import Body, File, Form, Query, Response, UploadFile
from fastapi.responses import HTMLResponse

from ogrl.api.handlers.objects import IfMatch
from ogrl.api.paths import integrations as i
from ogrl.api.registrar import CurrentPrincipal, Registrar
from ogrl.container import Container
from ogrl.errors import OGRLError
from ogrl.kernel.rules import SNAPSHOT_MEDIA_TYPE
from ogrl.operations.integrations import (
    CollectionRequest,
    ConnectionPatch,
    ConnectionWrite,
    DryRunRequest,
    InstallRequest,
    QueryWrite,
    RulePreviewRequest,
    SecretWrite,
    TemplateEnable,
)


def _page(title: str, message: str) -> str:
    return (
        "<!doctype html><meta charset=utf-8><title>OGRL</title>"
        f"<main style='font:16px system-ui;margin:4rem auto;max-width:32rem'>"
        f"<h1>{html.escape(title)}</h1><p>{html.escape(message)}</p></main>"
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

    async def install(body: InstallRequest, principal: CurrentPrincipal):
        return await s.install(principal, body)

    async def upload(
        principal: CurrentPrincipal,
        file: Annotated[UploadFile, File()],
        digest: Annotated[str | None, Form()] = None,
        enable: Annotated[bool, Form()] = True,
    ):
        return await s.install(principal, upload=await file.read(), expected=digest, enable=enable)

    async def list_versions(id: str, principal: CurrentPrincipal):
        return {"data": await s.list_versions(principal, id)}

    async def enable_version(id: str, version: str, principal: CurrentPrincipal):
        return await s.enable_version(principal, id, version)

    async def template_updates(id: str, principal: CurrentPrincipal):
        return {"data": await s.template_updates(principal, id)}

    async def apply_update(id: str, test_id: str, if_match: IfMatch, principal: CurrentPrincipal):
        return await s.apply_template_update(principal, id, test_id, if_match)

    registrar.handle(i.INSTALL_INTEGRATION, install)
    registrar.handle(i.UPLOAD_INTEGRATION, upload)
    registrar.handle(i.LIST_VERSIONS, list_versions)
    registrar.handle(i.ENABLE_VERSION, enable_version)
    registrar.handle(i.LIST_TEMPLATE_UPDATES, template_updates)
    registrar.handle(i.APPLY_TEMPLATE_UPDATE, apply_update)
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

    async def oauth_start(id: str, principal: CurrentPrincipal):
        return await s.oauth_start(principal, id)

    async def oauth_callback(
        state: str | None = None, code: str | None = None, error: str | None = None
    ) -> HTMLResponse:
        try:
            connection = await s.oauth_callback(state, code, error)
        except OGRLError as exc:
            return HTMLResponse(_page("Authorization failed", exc.detail), status_code=400)
        return HTMLResponse(
            _page(
                "Connected",
                f"{connection.name} is authorized. Validate it in OGRL; you can close this tab.",
            )
        )

    async def preview_rule(body: RulePreviewRequest, principal: CurrentPrincipal):
        return await s.preview_rule(principal, body)

    registrar.handle(i.PREVIEW_RULE, preview_rule)

    async def search_operations(
        id: str, principal: CurrentPrincipal, q: Annotated[str, Query()] = ""
    ):
        return {"data": await s.search_operations(principal, id, q)}

    async def describe_operation(id: str, operation: str, principal: CurrentPrincipal):
        return await s.describe_operation(principal, id, operation)

    async def validate_query(body: QueryWrite, principal: CurrentPrincipal):
        return await s.validate_query(principal, body)

    async def dry_run_query(body: DryRunRequest, principal: CurrentPrincipal):
        return await s.dry_run(principal, body)

    async def list_queries(principal: CurrentPrincipal):
        return {"data": await s.list_queries(principal)}

    async def create_query(body: QueryWrite, principal: CurrentPrincipal):
        return await s.create_query(principal, body)

    async def get_query(id: str, principal: CurrentPrincipal):
        return await s.get_query(principal, id)

    async def delete_query(id: str, principal: CurrentPrincipal) -> Response:
        await s.delete_query(principal, id)
        return Response(status_code=204)

    registrar.handle(i.SEARCH_OPERATIONS, search_operations)
    registrar.handle(i.DESCRIBE_OPERATION, describe_operation)
    registrar.handle(i.VALIDATE_QUERY, validate_query)
    registrar.handle(i.DRY_RUN_QUERY, dry_run_query)
    registrar.handle(i.LIST_QUERIES, list_queries)
    registrar.handle(i.CREATE_QUERY, create_query)
    registrar.handle(i.GET_QUERY, get_query)
    registrar.handle(i.DELETE_QUERY, delete_query)
    registrar.handle(i.OAUTH_START, oauth_start)
    registrar.handle(i.OAUTH_CALLBACK, oauth_callback)

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
