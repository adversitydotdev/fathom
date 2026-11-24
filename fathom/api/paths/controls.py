from http import HTTPMethod, HTTPStatus

from fathom.access import Permission
from fathom.api.paths.endpoint import Endpoint
from fathom.kernel.models import Control
from fathom.operations.pagination import Page

LIST_CONTROLS = Endpoint(
    id="listControls",
    summary="List library and custom controls.",
    method=HTTPMethod.GET,
    path="/controls",
    tag="Controls",
    permission=Permission.CONTROLS_READ,
    response=Page[Control],
)

CREATE_CONTROL = Endpoint(
    id="createControl",
    summary="Create a custom control.",
    description="`origin` is set to `custom`. A standard-library id is rejected.",
    method=HTTPMethod.POST,
    path="/controls",
    tag="Controls",
    permission=Permission.CONTROLS_WRITE,
    response=Control,
    success_status=HTTPStatus.CREATED,
)

GET_CONTROL = Endpoint(
    id="getControl",
    summary="Get one control.",
    method=HTTPMethod.GET,
    path="/controls/{id}",
    tag="Controls",
    permission=Permission.CONTROLS_READ,
    response=Control,
)

UPDATE_CONTROL = Endpoint(
    id="updateControl",
    summary="Update a custom control.",
    description="Library controls return 409. Arrays replace. `If-Match` is the current `modified`.",  # noqa: E501
    method=HTTPMethod.PATCH,
    path="/controls/{id}",
    tag="Controls",
    permission=Permission.CONTROLS_WRITE,
    response=Control,
)

REVOKE_CONTROL = Endpoint(
    id="revokeControl",
    summary="Revoke a custom control.",
    method=HTTPMethod.POST,
    path="/controls/{id}/revoke",
    tag="Controls",
    permission=Permission.CONTROLS_REVOKE,
    response=Control,
)

ALL = (LIST_CONTROLS, CREATE_CONTROL, GET_CONTROL, UPDATE_CONTROL, REVOKE_CONTROL)
