"""AWS STS for `aws_role` connections (RFC 0005 section 5)."""

import asyncio
from collections.abc import Mapping
from typing import Any

from ogrl.plugins.ports import IntegrationError


class StsRoleAssumer:
    def __init__(self, *, client: Any | None = None, region: str | None = None) -> None:
        self._client = client
        self._region = region

    def _sts(self) -> Any:
        """A new client per call. A reused client keeps its connection to an STS host that
        cached the role's old trust policy, and stays denied long after the operator fixes
        the trust (seen live: over 75 s, against 11 s for a fresh client)."""
        if self._client is not None:
            return self._client  # injected, for tests
        import boto3

        return boto3.client("sts", region_name=self._region)

    async def assume(self, role_arn: str, external_id: str, session_name: str) -> Mapping[str, str]:
        def call() -> Mapping[str, str]:
            response = self._sts().assume_role(
                RoleArn=role_arn,
                RoleSessionName=session_name,
                ExternalId=external_id,
                DurationSeconds=3600,
            )
            creds = response["Credentials"]
            return {
                "AWS_ACCESS_KEY_ID": creds["AccessKeyId"],
                "AWS_SECRET_ACCESS_KEY": creds["SecretAccessKey"],
                "AWS_SESSION_TOKEN": creds["SessionToken"],
            }

        try:
            return await asyncio.to_thread(call)
        except Exception as exc:  # botocore ClientError and friends
            raise IntegrationError("auth_failed", f"could not assume {role_arn}: {exc}") from exc
