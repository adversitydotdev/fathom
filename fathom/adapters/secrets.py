"""Secret resolution for the test harness (RFC 0003 sections 2 & 5)."""

from __future__ import annotations

import json
import logging
import os
import tempfile
from collections.abc import Mapping
from typing import Any

log = logging.getLogger(__name__)


class EnvSecrets:
    """Harness values from the process environment, as `FATHOM_HARNESS_<NAME>`.

    On AWS the task definition injects these from SSM under `harness/`
    (RFC 0003 section 2). A test names `IDP_TENANT`; the harness reads
    `FATHOM_HARNESS_IDP_TENANT` and passes it to the script as `IDP_TENANT`.
    """

    PREFIX = "FATHOM_HARNESS_"

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


class MemoryVault:
    """A `SecretVault` for tests. Lost when the process exits."""

    def __init__(self) -> None:
        self._values: dict[str, str] = {}

    def get(self, name: str) -> str | None:
        return self._values.get(name)

    def put(self, name: str, value: str) -> None:
        self._values[name] = value

    def delete(self, name: str) -> None:
        self._values.pop(name, None)


class FileVault:
    """A `SecretVault` in one JSON file readable only by its owner, for local development."""

    def __init__(self, path: str | os.PathLike[str]) -> None:
        self._path = os.fspath(path)

    def _read(self) -> dict[str, str]:
        try:
            with open(self._path) as handle:
                return json.load(handle)
        except FileNotFoundError:
            return {}

    def _write(self, values: dict[str, str]) -> None:
        directory = os.path.dirname(self._path) or "."
        os.makedirs(directory, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(dir=directory, prefix=".vault-")
        with os.fdopen(descriptor, "w") as handle:
            json.dump(values, handle, sort_keys=True)
        os.chmod(temporary, 0o600)
        os.replace(temporary, self._path)

    def get(self, name: str) -> str | None:
        return self._read().get(name)

    def put(self, name: str, value: str) -> None:
        values = self._read()
        values[name] = value
        self._write(values)

    def delete(self, name: str) -> None:
        values = self._read()
        if values.pop(name, None) is not None:
            self._write(values)


class SsmVault:
    """A `SecretVault` over SSM SecureString parameters under `{prefix}/harness/`."""

    def __init__(self, prefix: str, *, client: Any | None = None, region: str | None = None):
        self._prefix = prefix.rstrip("/")
        self._client = client
        self._region = region

    def _ssm(self) -> Any:
        if self._client is None:
            import boto3

            self._client = boto3.client("ssm", region_name=self._region)
        return self._client

    def _name(self, name: str) -> str:
        return f"{self._prefix}/harness/{name}"

    def get(self, name: str) -> str | None:
        try:
            response = self._ssm().get_parameter(Name=self._name(name), WithDecryption=True)
            return response["Parameter"]["Value"]
        except Exception:
            log.debug("SSM parameter %s not found or unreadable", self._name(name))
            return None

    def put(self, name: str, value: str) -> None:
        self._ssm().put_parameter(
            Name=self._name(name), Value=value, Type="SecureString", Overwrite=True
        )

    def delete(self, name: str) -> None:
        try:
            self._ssm().delete_parameter(Name=self._name(name))
        except Exception:
            log.debug("SSM parameter %s was already gone", self._name(name))
