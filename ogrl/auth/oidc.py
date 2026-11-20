"""Sign-in. Sketch only; nothing here is wired yet.

Flow, all on the API so it stays the only writer of the database:

    GET  /v1/auth/oidc/{provider}/begin     -> 302 to the IdP (PKCE + state + nonce)
    GET  /v1/auth/oidc/{provider}/callback  -> verify, upsert the person's party,
                                               create a session row, set
                                               __Host-ogrl_session, 302 to the app
    GET  /v1/auth/session                   -> who am I (Next.js middleware calls this)
    POST /v1/auth/logout                    -> revoke the session row, clear the cookie
    POST /v1/auth/tokens                    -> mint an API token for the CLI or an agent

Authlib does the OIDC client work (discovery, PKCE, ID token verification)
against Okta, Entra, Google, or Keycloak. A self-hosted install with no IdP
gets email magic links through the SES mail port instead.
"""

from typing import Protocol


class IdentityProvider(Protocol):
    name: str

    def authorization_url(self, state: str, nonce: str, code_verifier: str) -> str: ...

    async def exchange(self, code: str, code_verifier: str, nonce: str) -> "VerifiedIdentity": ...


class VerifiedIdentity(Protocol):
    issuer: str
    subject: str
    email: str | None
