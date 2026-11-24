from http import HTTPMethod

from pydantic import BaseModel

from fathom.api.paths.endpoint import Endpoint


class Health(BaseModel):
    status: str
    version: str


GET_HEALTH = Endpoint(
    id="getHealth",
    summary="Process health.",
    method=HTTPMethod.GET,
    path="/health",
    tag="Meta",
    authenticated=False,
    response=Health,
)

ALL = (GET_HEALTH,)
