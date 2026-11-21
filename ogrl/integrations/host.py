"""The integration process host: protocol version 1, RFC 0005 section 7.

One process per operation. The host writes `initialize`, checks the reply
against the installed manifest, writes exactly one operation, reads `log`
and `progress` notifications until the operation's response arrives, then
closes stdin. Stdout carries only JSON-RPC, one message per line. Stderr is
kept (truncated) for the error message.

The process gets a scratch directory as its working directory and `HOME`, a
fixed `PATH`, and the variables the caller passes. It never inherits the API's
environment. As with `shell`, this separates credentials; it is not a sandbox.
"""

import asyncio
import contextlib
import itertools
import json
import logging
import os
import platform
import shutil
import signal
import sys
import tempfile
from collections.abc import Mapping
from pathlib import Path
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
    ) -> CollectReport:
        def params(scratch: Path) -> dict[str, Any]:
            return {
                "resource": resource,
                "version": version,
                "config": dict(config),
                "output": str(scratch / "items.jsonl"),
            }

        def finish(scratch: Path, result: dict[str, Any]) -> CollectReport:
            complete = result.get("complete")
            if not isinstance(complete, bool):
                raise IntegrationError("protocol", "collect returned no complete flag")
            items = _read_items(scratch / "items.jsonl")
            count = result.get("count")
            if count is not None and count != len(items):
                raise IntegrationError(
                    "protocol", f"collect reported {count} items and wrote {len(items)}"
                )
            reason = result.get("reason")
            return CollectReport(items, complete, reason if isinstance(reason, str) else None)

        return await self._call(package, "collect", params, env, COLLECT_TIMEOUT, finish)

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
        def request(scratch: Path) -> dict[str, Any]:
            paths = {}
            for index, (source, content) in enumerate(sorted(snapshots.items())):
                path = scratch / f"snapshot-{index}.json"
                path.write_bytes(content)
                paths[source] = str(path)
            return {
                "check": check,
                "version": version,
                "args": dict(args),
                "params": dict(params),
                "snapshots": paths,
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

    def _command(self, package: Package) -> tuple[list[str], dict[str, str]]:
        runtime = package.manifest.runtime
        root = package.root.resolve()
        if runtime.kind == "python":
            module, _, function = runtime.entrypoint.partition(":")
            code = f"import {module} as m; m.{function or 'main'}()"
            # Pure-Python wheels under wheels/ (the SDK, for one) import straight from the zip.
            wheels = sorted(str(w) for w in (root / "wheels").glob("*.whl"))
            return [self._python, "-c", code], {"PYTHONPATH": os.pathsep.join([str(root), *wheels])}
        binary = root / "bin" / platform_tag() / runtime.entrypoint
        if not binary.is_file():
            raise IntegrationError("protocol", f"no {runtime.entrypoint} for {platform_tag()}")
        return [str(binary)], {}

    async def _call(
        self,
        package: Package,
        method: str,
        params: Any,
        secrets: Mapping[str, str],
        time_limit: int,
        finish: Any = None,
    ) -> Any:
        scratch = Path(tempfile.mkdtemp(prefix="ogrl-integration-"))
        process: asyncio.subprocess.Process | None = None
        stderr_task: asyncio.Task[bytes] | None = None
        try:
            if self._user:
                shutil.chown(scratch, user=self._user)
            argv, runtime_env = self._command(package)
            env = {
                "PATH": DEFAULT_PATH,
                "HOME": str(scratch),
                "LANG": "C.UTF-8",
                **runtime_env,
                **secrets,
            }
            body = params(scratch) if callable(params) else params
            process = await asyncio.create_subprocess_exec(
                *argv,
                cwd=scratch,
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
                    self._converse(process, package, method, body), timeout=time_limit
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
            return finish(scratch, result) if finish else result
        finally:
            if process is not None and process.returncode is None:
                with contextlib.suppress(ProcessLookupError):
                    os.killpg(process.pid, signal.SIGKILL)
                await process.wait()
            if stderr_task is not None:
                stderr_task.cancel()
            shutil.rmtree(scratch, ignore_errors=True)

    async def _converse(
        self, process: asyncio.subprocess.Process, package: Package, method: str, params: Any
    ) -> dict[str, Any]:
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
        return await self._request(process, method, params)

    async def _request(
        self, process: asyncio.subprocess.Process, method: str, params: Any
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
            if "id" not in message:  # a notification: log or progress
                if message.get("method") == "log":
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


def _read_items(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    items = []
    with path.open("rb") as handle:
        for number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                raise IntegrationError("protocol", f"items line {number} is not JSON") from None
            if not isinstance(item, dict):
                raise IntegrationError("protocol", f"items line {number} is not an object")
            items.append(item)
    return items


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
