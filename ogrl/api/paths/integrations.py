"""Integrations, connections, and snapshots (RFC 0005)."""

from http import HTTPMethod, HTTPStatus

from ogrl.access import Permission as P
from ogrl.api.paths.endpoint import Endpoint
from ogrl.kernel.models import Test
from ogrl.operations.connections import Connection, Snapshot
from ogrl.operations.integrations import IntegrationView
from ogrl.operations.records import Job
from ogrl.operations.views import DataList

GET, POST, PATCH, PUT, DELETE = (
    HTTPMethod.GET,
    HTTPMethod.POST,
    HTTPMethod.PATCH,
    HTTPMethod.PUT,
    HTTPMethod.DELETE,
)

LIST_INTEGRATIONS = Endpoint(
    id="listIntegrations",
    summary="List integrations installed in this deployment.",
    method=GET,
    path="/integrations",
    tag="Integrations",
    permission=P.PROGRAMS_READ,
    response=DataList[IntegrationView],
)
GET_INTEGRATION = Endpoint(
    id="getIntegration",
    summary="Get one installed integration.",
    method=GET,
    path="/integrations/{id}",
    tag="Integrations",
    permission=P.PROGRAMS_READ,
    response=IntegrationView,
)
ENABLE_TEMPLATE = Endpoint(
    id="enableIntegrationTemplate",
    summary="Create an organization test from an integration's template.",
    method=POST,
    path="/integrations/{id}/templates/{name}/enable",
    tag="Integrations",
    permission=P.TESTS_DEFINE_RUN,
    response=Test,
    success_status=HTTPStatus.CREATED,
)
LIST_CONNECTIONS = Endpoint(
    id="listConnections",
    summary="List connections to vendor accounts.",
    method=GET,
    path="/connections",
    tag="Connections",
    permission=P.PROGRAMS_READ,
    response=DataList[Connection],
)
CREATE_CONNECTION = Endpoint(
    id="createConnection",
    summary="Connect an installed integration to a vendor account.",
    method=POST,
    path="/connections",
    tag="Connections",
    permission=P.INTEGRATIONS_MANAGE,
    response=Connection,
    success_status=HTTPStatus.CREATED,
)
GET_CONNECTION = Endpoint(
    id="getConnection",
    summary="Get one connection.",
    method=GET,
    path="/connections/{id}",
    tag="Connections",
    permission=P.PROGRAMS_READ,
    response=Connection,
)
UPDATE_CONNECTION = Endpoint(
    id="updateConnection",
    summary="Rename, reconfigure, rebind, disable, or re-enable a connection.",
    method=PATCH,
    path="/connections/{id}",
    tag="Connections",
    permission=P.INTEGRATIONS_MANAGE,
    response=Connection,
)
DELETE_CONNECTION = Endpoint(
    id="deleteConnection",
    summary="Remove a connection and its secrets.",
    method=DELETE,
    path="/connections/{id}",
    tag="Connections",
    permission=P.INTEGRATIONS_MANAGE,
    success_status=HTTPStatus.NO_CONTENT,
)
SET_SECRET = Endpoint(
    id="setConnectionSecret",
    summary="Write one secret value. Write-only; values are never returned.",
    method=PUT,
    path="/connections/{id}/secrets/{name}",
    tag="Connections",
    permission=P.INTEGRATIONS_MANAGE,
    response=Connection,
)
VALIDATE_CONNECTION = Endpoint(
    id="validateConnection",
    summary="Check the connection's credentials with the vendor. Returns a job.",
    method=POST,
    path="/connections/{id}/validate",
    tag="Connections",
    permission=P.COLLECTIONS_RUN,
    response=Job,
    success_status=HTTPStatus.ACCEPTED,
)
COLLECT = Endpoint(
    id="collectConnection",
    summary="Collect snapshots now. Returns a job.",
    method=POST,
    path="/connections/{id}/collections",
    tag="Connections",
    permission=P.COLLECTIONS_RUN,
    response=Job,
    success_status=HTTPStatus.ACCEPTED,
)
LIST_SNAPSHOTS = Endpoint(
    id="listSnapshots",
    summary="List collected snapshots, newest first.",
    method=GET,
    path="/snapshots",
    tag="Snapshots",
    permission=P.PROGRAMS_READ,
    response=DataList[Snapshot],
)
GET_SNAPSHOT = Endpoint(
    id="getSnapshot",
    summary="Get one snapshot's metadata.",
    method=GET,
    path="/snapshots/{id}",
    tag="Snapshots",
    permission=P.PROGRAMS_READ,
    response=Snapshot,
)
GET_SNAPSHOT_CONTENT = Endpoint(
    id="getSnapshotContent",
    summary="Download the snapshot document (RFC 0001 section 7.6).",
    method=GET,
    path="/snapshots/{id}/content",
    tag="Snapshots",
    permission=P.PROGRAMS_READ,
)

ALL = (
    LIST_INTEGRATIONS,
    GET_INTEGRATION,
    ENABLE_TEMPLATE,
    LIST_CONNECTIONS,
    CREATE_CONNECTION,
    GET_CONNECTION,
    UPDATE_CONNECTION,
    DELETE_CONNECTION,
    SET_SECRET,
    VALIDATE_CONNECTION,
    COLLECT,
    LIST_SNAPSHOTS,
    GET_SNAPSHOT,
    GET_SNAPSHOT_CONTENT,
)
