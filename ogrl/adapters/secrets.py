"""Secret resolution for the test harness (RFC 0003 sections 2 & 5)."""

from __future__ import annotations

import logging
import os
from collections.abc import Mapping
from typing import Any

log = logging.getLogger(__name__)


class EnvSecrets:
    """Harness values from the process environment, as `OGRL_HARNESS_<NAME>`.

    On AWS the task definition injects these from SSM under `harness/`
    (RFC 0003 section 2). A test names `IDP_TENANT`; the harness reads
    `OGRL_HARNESS_IDP_TENANT` and passes it to the script as `IDP_TENANT`.
    """

    PREFIX = "OGRL_HARNESS_"

    def __init__(self, environ: Mapping[str, str] | None = None) -> None:
        self._environ = environ if environ is not None else os.environ

    def get(self, name: str) -> str | None:
        return self._environ.get(self.PREFIX + name)


class StaticSecrets:
    def __init__(self, values: Mapping[str, str] | None = None) -> None:
        self._values = dict(values or {})

    def get(self, name: str) -> str | None:
        return self._values.get(name)


class SsmSecrets:
    """Reads `{prefix}/harness/{name}` from AWS SSM Parameter Store, with env fallback."""

    def __init__(
        self,
        prefix: str,
        *,
        fallback: EnvSecrets | None = None,
        client: Any | None = None,
        region: str | None = None,
    ) -> None:
        self._prefix = prefix.rstrip("/")
        self._fallback = fallback or EnvSecrets()
        self._client = client
        self._region = region

    def _ssm(self) -> Any:
        if self._client is None:
            import boto3

            self._client = boto3.client("ssm", region_name=self._region)
        return self._client

    def get(self, name: str) -> str | None:
        env_val = self._fallback.get(name)
        if env_val is not None:
            return env_val
        param_name = f"{self._prefix}/harness/{name}"
        try:
            resp = self._ssm().get_parameter(Name=param_name, WithDecryption=True)
            return resp["Parameter"]["Value"]
        except Exception:
            log.debug("SSM parameter %s not found or unreadable", param_name)
            return None
