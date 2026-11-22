"""The integration process host: protocol version 1, RFC 0005 section 7.

One process per operation. The host writes `initialize`, checks the reply
against the installed manifest, writes exactly one operation, reads `log`
and `progress` notifications until the operation's response arrives, then
closes stdin. Stdout carries only JSON-RPC, one message per line. Stderr is
kept (truncated) for the error message.

Nothing touches the filesystem, so OGRL runs on a read-only root: items stream
back as `items` notifications, snapshots go inside the `check` request, and
an installed (archive) package is loaded from memory. The host starts
`python -I` with BOOTSTRAP, writes the package's `.py` files and wheels as the
first stdin line, and the bootstrap serves them to `import` from memory.
Directory packages import from their (possibly read-only) directory.

The process gets a fixed `PATH`, `PYTHONDONTWRITEBYTECODE`, and the variables
the caller passes, with no `HOME`. It never inherits the API's environment. As
with `shell`, this separates credentials; it is not a sandbox.
"""

import asyncio
import base64
import contextlib
import itertools
import json
import logging
import os
import platform
import signal
import sys
from collections.abc import Mapping
from typing import Any

from ogrl.integrations.manifest import PROTOCOL_VERSION, Package
from ogrl.plugins.ports import CheckReport, CollectReport, IntegrationError, ValidateReport

log = logging.getLogger(__name__)

DEFAULT_PATH = "/usr/local/bin:/usr/bin:/bin"
STDERR_LIMIT = 64 * 1024
LINE_LIMIT = 1024 * 1024
EXIT_GRACE = 10
VALIDATE_TIMEOUT = 30
COLLECT_TIMEOUT = 15 * 60
ERROR_KINDS = frozenset(
    {"auth_failed", "permission_denied", "rate_limited", "vendor_error", "invalid_config"}
)


def platform_tag() -> str:
    """`linux-arm64`, `darwin-arm64`, ...: the `bin/<platform>/` directory of a binary package."""
    system = "darwin" if sys.platform == "darwin" else sys.platform
    machine = platform.machine().lower()
    arch = {"x86_64": "amd64", "amd64": "amd64", "aarch64": "arm64", "arm64": "arm64"}.get(
        machine, machine
    )
    return f"{system}-{arch}"


BOOTSTRAP = r"""
import base64, importlib.abc, importlib.util, io, json, sys, zipfile
_bundle = json.loads(sys.stdin.readline())["files"]
_sources = {}
def _add(path, data, origin):
    if not path.endswith(".py"):
        return
    parts = path[:-3].split("/")
    package = parts[-1] == "__init__"
    name = ".".join(parts[:-1] if package else parts)
    if name and all(p.isidentifier() for p in name.split(".")):
        _sources.setdefault(name, (data, package, origin + path))
for _path in sorted(_bundle):  # the package's own modules win over its wheels
    if not _path.startswith(("wheels/", "tests/")):
        _add(_path, base64.b64decode(_bundle[_path]), "<ogrl-package>/")
for _path in sorted(_bundle):
    if _path.startswith("wheels/") and _path.endswith(".whl"):
        with zipfile.ZipFile(io.BytesIO(base64.b64decode(_bundle[_path]))) as _wheel:
            for _member in _wheel.namelist():
                if ".dist-info/" not in _member and ".data/" not in _member:
                    _add(_member, _wheel.read(_member), "<ogrl-package>/" + _path + "/")
del _bundle
class _MemoryImporter(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    def find_spec(self, name, path=None, target=None):
        if name not in _sources:
            return None
        _, package, origin = _sources[name]
        return importlib.util.spec_from_loader(name, self, origin=origin, is_package=package)
    def create_module(self, spec):
        return None
    def exec_module(self, module):
        data, _, origin = _sources[module.__spec__.name]
        module.__file__ = origin
        exec(compile(data, origin, "exec"), module.__dict__)
sys.meta_path.insert(0, _MemoryImporter())
"""


class SubprocessHost:
    def __init__(self, *, user: str | None = None, python: str = sys.executable) -> None:
        self._user = user
        self._python = python
        self._ids = itertools.count(1)

    # --- operations ----------------------------------------------------------------------------

    async def validate(
        self, package: Package, config: Mapping[str, str], env: Mapping[str, str]
    ) -> ValidateReport:
        result = await self._call(
            package, "connection.validate", {"config": dict(config)}, env, VALIDATE_TIMEOUT
        )
        identity = result.get("identity")
        if not isinstance(identity, str) or not identity:
            raise IntegrationError("protocol", "connection.validate returned no identity")
        return ValidateReport(
            identity=identity,
            granted_scopes=_strings(result.get("granted_scopes")),
            warnings=_strings(result.get("warnings")),
        )

    async def collect(
        self,
        package: Package,
        resource: str,
        version: int,
        config: Mapping[str, str],
        env: Mapping[str, str],
        query: Mapping[str, Any] | None = None,
    ) -> CollectReport:
        items: list[dict[str, Any]] = []
        params: dict[str, Any] = {"resource": resource, "version": version, "config": dict(config)}
        if query is not None:  # a query source (RFC 0006)
            params["query"] = dict(query)
        result = await self._call(package, "collect", params, env, COLLECT_TIMEOUT, items)
        complete = result.get("complete")
        if not isinstance(complete, bool):
            raise IntegrationError("protocol", "collect returned no complete flag")
        count = result.get("count")
        if count is not None and count != len(items):
            raise IntegrationError(
                "protocol", f"collect reported {count} items and sent {len(items)}"
            )
        reason = result.get("reason")
        return CollectReport(items, complete, reason if isinstance(reason, str) else None)

    async def check(
        self,
        package: Package,
        check: str,
        version: int,
        args: Mapping[str, str],
        params: Mapping[str, str],
        snapshots: Mapping[str, bytes],
        time_limit: int,
    ) -> CheckReport:
        request = {
            "check": check,
            "version": version,
            "args": dict(args),
            "params": dict(params),
            "snapshots": {source: json.loads(content) for source, content in snapshots.items()},
        }
        # A check holds no credentials (RFC 0005 section 7).
        result = await self._call(package, "check", request, {}, time_limit)
        outcome = result.get("outcome")
        if outcome not in ("pass", "fail", "error"):
            raise IntegrationError("protocol", f"check returned outcome {outcome!r}")
        summary = result.get("summary")
        subjects = result.get("subjects") or []
        if not isinstance(subjects, list) or not all(
            isinstance(s, dict)
            and isinstance(s.get("kind"), str)
            and isinstance(s.get("name"), str)
            for s in subjects
        ):
            raise IntegrationError("protocol", "check subjects need kind and name strings")
        return CheckReport(
            outcome=outcome,
            summary=summary[:2048] if isinstance(summary, str) else "",
            subjects=[
                {k: str(v) for k, v in s.items() if k in ("kind", "name", "external_id")}
                for s in subjects
            ],
        )

    # --- process -------------------------------------------------------------------------------

    def _command(self, package: Package) -> tuple[list[str], bytes | None, str]:
        """argv, the bundle line to write before the protocol (in-memory packages), and cwd."""
        runtime = package.manifest.runtime
        module, _, function = runtime.entrypoint.partition(":")
        start = f"import {module} as m; m.{function or 'main'}()"
        if runtime.kind == "python" and package.root is None:
            bundle = {
                "files": {
                    name: base64.b64encode(data).decode()
                    for name, data in package.files.items()
                    if name.endswith((".py", ".whl"))
                }
            }
            line = json.dumps(bundle, separators=(",", ":")).encode() + b"\n"
            return [self._python, "-I", "-c", BOOTSTRAP + start], line, "/"
        if package.root is None:
            raise IntegrationError(
                "protocol", "binary packages run from a directory (OGRL_INTEGRATIONS_DIR)"
            )
        root = package.root.resolve()
        if runtime.kind == "python":
            # Pure-Python wheels under wheels/ (the SDK, for one) import straight from the zip.
            paths = [str(root), *sorted(str(w) for w in (root / "wheels").glob("*.whl"))]
            return (
                [self._python, "-I", "-c", f"import sys; sys.path[:0] = {paths!r}; {start}"],
                None,
                str(root),
            )
        binary = root / "bin" / platform_tag() / runtime.entrypoint
        if not binary.is_file():
            raise IntegrationError("protocol", f"no {runtime.entrypoint} for {platform_tag()}")
        return [str(binary)], None, str(root)

    async def _call(
        self,
        package: Package,
        method: str,
        params: dict[str, Any],
        secrets: Mapping[str, str],
        time_limit: int,
        items: list[dict[str, Any]] | None = None,
    ) -> Any:
        """Run one operation. Nothing touches the filesystem (RFC 0005 section 7)."""
        process: asyncio.subprocess.Process | None = None
        stderr_task: asyncio.Task[bytes] | None = None
        try:
            argv, bundle, cwd = self._command(package)
            env = {
                "PATH": DEFAULT_PATH,
                "LANG": "C.UTF-8",
                "PYTHONDONTWRITEBYTECODE": "1",
                **secrets,
            }
            process = await asyncio.create_subprocess_exec(
                *argv,
                cwd=cwd,
                env=env,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                start_new_session=True,
                user=self._user,
                limit=LINE_LIMIT,
            )
            stderr_task = asyncio.create_task(_drain(process.stderr))
            try:
                result = await asyncio.wait_for(
                    self._converse(process, package, method, params, bundle, items),
                    timeout=time_limit,
                )
            except TimeoutError:
                message = f"{method} timed out after {time_limit}s"
                raise IntegrationError("protocol", message) from None
            except IntegrationError as exc:
                if exc.kind == "protocol":
                    detail = await _stderr_tail(stderr_task)
                    if detail:
                        exc.message = f"{exc.message}: {detail}"
                        exc.args = (exc.message,)
                raise
            if process.stdin and not process.stdin.is_closing():
                process.stdin.close()
            try:
                await asyncio.wait_for(process.wait(), timeout=EXIT_GRACE)
            except TimeoutError:
                log.warning("%s did not exit after %s; killed", package.id, method)
            return result
        finally:
            if process is not None and process.returncode is None:
                with contextlib.suppress(ProcessLookupError):
                    os.killpg(process.pid, signal.SIGKILL)
                await process.wait()
            if stderr_task is not None:
                stderr_task.cancel()

    async def _converse(
        self,
        process: asyncio.subprocess.Process,
        package: Package,
        method: str,
        params: Any,
        bundle: bytes | None,
        items: list[dict[str, Any]] | None,
    ) -> dict[str, Any]:
        if bundle is not None:
            assert process.stdin
            try:
                process.stdin.write(bundle)
                await process.stdin.drain()
            except (BrokenPipeError, ConnectionResetError):
                raise IntegrationError("protocol", "the process exited before loading") from None
        hello = await self._request(process, "initialize", {"protocol": PROTOCOL_VERSION})
        if (
            hello.get("protocol") != PROTOCOL_VERSION
            or hello.get("id") != package.manifest.id
            or hello.get("version") != package.manifest.version
        ):
            raise IntegrationError(
                "protocol",
                f"initialize answered {hello.get('id')} {hello.get('version')} protocol "
                f"{hello.get('protocol')}; installed is {package.manifest.id} "
                f"{package.manifest.version} protocol {PROTOCOL_VERSION}",
            )
        return await self._request(process, method, params, items)

    async def _request(
        self,
        process: asyncio.subprocess.Process,
        method: str,
        params: Any,
        items: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        assert process.stdin and process.stdout
        request_id = next(self._ids)
        line = json.dumps({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
        try:
            process.stdin.write(line.encode() + b"\n")
            await process.stdin.drain()
        except (BrokenPipeError, ConnectionResetError):
            raise IntegrationError("protocol", f"the process exited before {method}") from None
        while True:
            try:
                raw = await process.stdout.readline()
            except ValueError:
                raise IntegrationError("protocol", "a stdout line exceeded 1 MB") from None
            if not raw:
                raise IntegrationError("protocol", f"the process exited during {method}")
            try:
                message = json.loads(raw)
            except json.JSONDecodeError:
                raise IntegrationError(
                    "protocol", "stdout carried a line that is not JSON"
                ) from None
            if not isinstance(message, dict):
                raise IntegrationError("protocol", "stdout carried a message that is not an object")
            if "id" not in message:  # a notification: items, log, or progress
                if message.get("method") == "items":
                    batch = (message.get("params") or {}).get("items")
                    if items is None or not isinstance(batch, list):
                        raise IntegrationError("protocol", "items arrived outside collect")
                    if not all(isinstance(i, dict) for i in batch):
                        raise IntegrationError("protocol", "an item is not an object")
                    items.extend(batch)
                elif message.get("method") == "log":
                    log.info("integration: %s", (message.get("params") or {}).get("message"))
                continue
            if message.get("id") != request_id:
                raise IntegrationError("protocol", "a response answered another request")
            if "error" in message:
                raise _error(message["error"])
            result = message.get("result")
            if not isinstance(result, dict):
                raise IntegrationError("protocol", f"{method} returned no result object")
            return result


def _error(error: Any) -> IntegrationError:
    if not isinstance(error, dict):
        return IntegrationError("protocol", "a malformed error")
    data = error.get("data") if isinstance(error.get("data"), dict) else {}
    kind = data.get("kind")
    retry = data.get("retry_after")
    return IntegrationError(
        kind if kind in ERROR_KINDS else "vendor_error",
        str(error.get("message") or "the integration failed"),
        retry if isinstance(retry, int) else None,
    )


def _strings(value: Any) -> list[str]:
    return [str(v) for v in value] if isinstance(value, list) else []


async def _drain(stream: asyncio.StreamReader | None) -> bytes:
    if stream is None:
        return b""
    kept = bytearray()
    while chunk := await stream.read(65536):
        if len(kept) < STDERR_LIMIT:
            kept.extend(chunk[: STDERR_LIMIT - len(kept)])
    return bytes(kept)


async def _stderr_tail(task: asyncio.Task[bytes]) -> str:
    with contextlib.suppress(Exception):
        data = await asyncio.wait_for(asyncio.shield(task), timeout=1)
        lines = [line for line in data.decode(errors="replace").splitlines() if line.strip()]
        return lines[-1][:500] if lines else ""
    return ""
