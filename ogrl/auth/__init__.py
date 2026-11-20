"""Who is calling: sessions for the browser, API tokens for everything else."""

from ogrl.auth.authenticator import (
    API_TOKEN_PREFIX,
    SESSION_COOKIE,
    ApiTokenAuthenticator,
    Authenticator,
    ChainAuthenticator,
    Credentials,
    SessionAuthenticator,
)

__all__ = [
    "API_TOKEN_PREFIX",
    "SESSION_COOKIE",
    "ApiTokenAuthenticator",
    "Authenticator",
    "ChainAuthenticator",
    "Credentials",
    "SessionAuthenticator",
]
