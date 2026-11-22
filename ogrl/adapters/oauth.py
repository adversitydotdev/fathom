"""The vendor OAuth token endpoint over HTTP (RFC 0005 section 5)."""

from collections.abc import Mapping
from typing import Any

import httpx

from ogrl.plugins.ports import IntegrationError


class HttpOAuthClient:
    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._transport = transport

    async def token(self, token_url: str, form: Mapping[str, str]) -> Mapping[str, Any]:
        try:
            async with httpx.AsyncClient(transport=self._transport, timeout=30) as client:
                response = await client.post(
                    token_url, data=dict(form), headers={"Accept": "application/json"}
                )
        except httpx.HTTPError as exc:
            raise IntegrationError("vendor_error", f"token endpoint unreachable: {exc}") from exc
        try:
            body = response.json()
        except ValueError:
            body = {}
        if response.status_code >= 400 or not isinstance(body, dict):
            error = (
                body.get("error_description") or body.get("error")
                if isinstance(body, dict)
                else None
            )
            raise IntegrationError(
                "auth_failed",
                f"token endpoint answered {response.status_code}: {error or 'no detail'}",
            )
        return body
