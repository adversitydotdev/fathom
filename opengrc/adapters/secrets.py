import os
from collections.abc import Mapping


class EnvSecrets:
    """Harness values from the process environment, as `OPENGRC_HARNESS_<NAME>`.

    On AWS the task definition injects these from SSM under `harness/`
    (RFC 0003 section 2). A test names `IDP_TENANT`; the harness reads
    `OPENGRC_HARNESS_IDP_TENANT` and passes it to the script as `IDP_TENANT`.
    """

    PREFIX = "OPENGRC_HARNESS_"

    def __init__(self, environ: Mapping[str, str] | None = None) -> None:
        self._environ = environ if environ is not None else os.environ

    def get(self, name: str) -> str | None:
        return self._environ.get(self.PREFIX + name)


class StaticSecrets:
    def __init__(self, values: Mapping[str, str] | None = None) -> None:
        self._values = dict(values or {})

    def get(self, name: str) -> str | None:
        return self._values.get(name)
