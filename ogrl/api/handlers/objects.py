"""Handlers for every object collection: parse, call one operation, shape the response.

One factory per kind of route. The query model comes from the type's spec,
so FastAPI validates filters the same way the spec declares them. No rules
live here; `ObjectService` owns them.
"""

from datetime import datetime
from typing import Annotated, Any

from fastapi import Body, Header, Query, Response

from ogrl.api.paths.collections import Collection, SubList
from ogrl.api.registrar import CurrentPrincipal, Registrar
from ogrl.operations.objects import ObjectService
from ogrl.operations.pagination import PageRequest
from ogrl.operations.store import Row
from ogrl.operations.types import valid_on

IfMatch = Annotated[datetime, Header(alias="If-Match")]
JsonObject = Annotated[dict[str, Any], Body()]


def register_collection(registrar: Registrar, service: ObjectService, c: Collection) -> None:
    spec = c.spec
    get_endpoint = c.get

    if c.index is not None:
        query_model = spec.query

        async def list_objects(
            principal: CurrentPrincipal,
            query: Annotated[query_model, Query()],  # type: ignore[valid-type]
        ):
            return await service.list(principal, spec, query)

        registrar.handle(c.index, list_objects)

    if c.get is not None:

        async def get_object(id: str, principal: CurrentPrincipal):
            return await service.get(principal, spec, id)

        registrar.handle(c.get, get_object)

    if c.create is not None:

        async def create_object(body: JsonObject, principal: CurrentPrincipal, response: Response):
            obj = await service.create(principal, spec, body)
            if get_endpoint is not None:
                response.headers["Location"] = get_endpoint.url(id=obj.id)
            return obj

        registrar.handle(c.create, create_object)

    if c.update is not None:

        async def update_object(
            id: str, body: JsonObject, if_match: IfMatch, principal: CurrentPrincipal
        ):
            return await service.update(principal, spec, id, body, if_match)

        registrar.handle(c.update, update_object)

    if c.revoke is not None:

        async def revoke_object(id: str, if_match: IfMatch, principal: CurrentPrincipal):
            return await service.revoke(principal, spec, id, if_match)

        registrar.handle(c.revoke, revoke_object)

    for sub in c.subs:
        register_sub(registrar, service, sub)


def register_sub(registrar: Registrar, service: ObjectService, sub: SubList) -> None:
    query_model: type[PageRequest] = sub.query

    async def list_children(
        id: str,
        principal: CurrentPrincipal,
        query: Annotated[query_model, Query()],  # type: ignore[valid-type]
    ):
        await service.get(principal, sub.parent, id)  # 404 when the parent is unknown

        def scope(row: Row) -> bool:
            if getattr(row.obj, sub.field, None) is None:
                return False
            value = getattr(row.obj, sub.field)
            if sub.field == "target_ref":
                value = value.partition("#")[0]
            return value == id and _filters(row, query)

        return await service.list(principal, sub.spec, sub.spec.query(**_page(query)), scope)

    registrar.handle(sub.endpoint, list_children)


def _page(query: PageRequest) -> dict[str, Any]:
    return {"limit": query.limit, "cursor": query.cursor}


def _filters(row: Row, query: PageRequest) -> bool:
    """The few filters sub-collections take: system_id, outcome, valid_on."""
    system_id = getattr(query, "system_id", None)
    if system_id is not None and getattr(row.obj, "system_ref", None) != system_id:
        return False
    outcome = getattr(query, "outcome", None)
    if outcome is not None and getattr(row.obj, "outcome", None) != outcome:
        return False
    day = getattr(query, "valid_on", None)
    return day is None or valid_on(row.obj, day)  # type: ignore[arg-type]
