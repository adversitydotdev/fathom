"""Integrations, connections, and snapshots (RFC 0005)."""

from http import HTTPMethod, HTTPStatus

from ogrl.access import Permission as P
from ogrl.api.paths.endpoint import Endpoint
from ogrl.kernel.models import Test
from ogrl.operations.connections import Connection, InstallRecord, Snapshot
from ogrl.operations.integrations import IntegrationView, OAuthStart, TemplateUpdate
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
INSTALL_INTEGRATION = Endpoint(
    id="installIntegration",
    summary="Install an integration archive from a URL. Returns a job.",
    method=POST,
    path="/integrations",
    tag="Integrations",
    permission=P.INTEGRATIONS_MANAGE,
    response=Job,
    success_status=HTTPStatus.ACCEPTED,
)
UPLOAD_INTEGRATION = Endpoint(
    id="uploadIntegration",
    summary="Install an uploaded integration archive. Returns a job.",
    method=POST,
    path="/integrations/archives",
    tag="Integrations",
    permission=P.INTEGRATIONS_MANAGE,
    response=Job,
    success_status=HTTPStatus.ACCEPTED,
)
LIST_VERSIONS = Endpoint(
    id="listIntegrationVersions",
    summary="List the installed archive versions of an integration.",
    method=GET,
    path="/integrations/{id}/versions",
    tag="Integrations",
    permission=P.PROGRAMS_READ,
    response=DataList[InstallRecord],
)
ENABLE_VERSION = Endpoint(
    id="enableIntegrationVersion",
    summary="Enable an installed version: an upgrade or a rollback.",
    method=POST,
    path="/integrations/{id}/versions/{version}/enable",
    tag="Integrations",
    permission=P.INTEGRATIONS_MANAGE,
    response=IntegrationView,
)
LIST_TEMPLATE_UPDATES = Endpoint(
    id="listTemplateUpdates",
    summary="Tests whose template changed in the enabled version.",
    method=GET,
    path="/integrations/{id}/template-updates",
    tag="Integrations",
    permission=P.PROGRAMS_READ,
    response=DataList[TemplateUpdate],
)
APPLY_TEMPLATE_UPDATE = Endpoint(
    id="applyTemplateUpdate",
    summary="Accept a template update for one test.",
    method=POST,
    path="/integrations/{id}/template-updates/{test_id}/apply",
    tag="Integrations",
    permission=P.TESTS_DEFINE_RUN,
    response=Test,
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
OAUTH_START = Endpoint(
    id="startConnectionOAuth",
    summary="Begin bring-your-own OAuth: the vendor URL to send the operator to.",
    method=POST,
    path="/connections/{id}/oauth/start",
    tag="Connections",
    permission=P.INTEGRATIONS_MANAGE,
    response=OAuthStart,
)
OAUTH_CALLBACK = Endpoint(
    id="finishConnectionOAuth",
    summary="The vendor's redirect after authorization. Public; protected by single-use state.",
    method=GET,
    path="/oauth/callback",
    tag="Connections",
    authenticated=False,
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
    INSTALL_INTEGRATION,
    UPLOAD_INTEGRATION,
    LIST_VERSIONS,
    ENABLE_VERSION,
    LIST_TEMPLATE_UPDATES,
    APPLY_TEMPLATE_UPDATE,
    LIST_CONNECTIONS,
    CREATE_CONNECTION,
    GET_CONNECTION,
    UPDATE_CONNECTION,
    DELETE_CONNECTION,
    SET_SECRET,
    VALIDATE_CONNECTION,
    COLLECT,
    OAUTH_START,
    OAUTH_CALLBACK,
    LIST_SNAPSHOTS,
    GET_SNAPSHOT,
    GET_SNAPSHOT_CONTENT,
)
