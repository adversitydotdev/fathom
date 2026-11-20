"""Authentication endpoints: OIDC login, session lookup, logout, and API token minting."""

from http import HTTPMethod, HTTPStatus

from ogrl.api.paths.endpoint import Endpoint
from ogrl.auth.store import TokenRecord
from ogrl.operations.auth import CreatedToken, SessionInfo
from ogrl.operations.views import DataList

GET, POST = HTTPMethod.GET, HTTPMethod.POST

OIDC_BEGIN = Endpoint(
    id="beginOidcLogin",
    summary="Redirect to an OIDC identity provider with PKCE.",
    method=GET,
    path="/auth/oidc/{provider}/begin",
    tag="Auth",
    authenticated=False,
    success_status=HTTPStatus.FOUND,
)
OIDC_CALLBACK = Endpoint(
    id="finishOidcLogin",
    summary="Verify OIDC callback, upsert party, and set session cookie.",
    method=GET,
    path="/auth/oidc/{provider}/callback",
    tag="Auth",
    authenticated=False,
    success_status=HTTPStatus.FOUND,
)
GET_SESSION = Endpoint(
    id="getAuthSession",
    summary="Describe the currently authenticated principal.",
    method=GET,
    path="/auth/session",
    tag="Auth",
    response=SessionInfo,
)
LOGOUT = Endpoint(
    id="logoutSession",
    summary="Revoke the active browser session and clear its cookie.",
    method=POST,
    path="/auth/logout",
    tag="Auth",
    success_status=HTTPStatus.NO_CONTENT,
)
LIST_TOKENS = Endpoint(
    id="listAuthTokens",
    summary="List API token metadata (never plaintext).",
    method=GET,
    path="/auth/tokens",
    tag="Auth",
    response=DataList[TokenRecord],
)
CREATE_TOKEN = Endpoint(
    id="createAuthToken",
    summary="Mint a new API token for the caller or a managed actor.",
    method=POST,
    path="/auth/tokens",
    tag="Auth",
    response=CreatedToken,
    success_status=HTTPStatus.CREATED,
)
REVOKE_TOKEN = Endpoint(
    id="revokeAuthToken",
    summary="Revoke a minted API token.",
    method=POST,
    path="/auth/tokens/{id}/revoke",
    tag="Auth",
    success_status=HTTPStatus.NO_CONTENT,
)

ALL = (
    OIDC_BEGIN,
    OIDC_CALLBACK,
    GET_SESSION,
    LOGOUT,
    LIST_TOKENS,
    CREATE_TOKEN,
    REVOKE_TOKEN,
)
