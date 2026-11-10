"""The `shell` runner: the harness contract in RFC 0001 section 7.6.

1. A scratch directory per run, discarded after.
2. The environment is the `run.env` values, the `OGRC_` variables, and a
   fixed PATH. Nothing from the API's own environment is inherited, so the
   script never sees the database credential or cloud credentials.
3. `command` is written to a file and executed with `sh` in the scratch dir.
4. `timeout` kills the process group; a timeout is `error`.
5. Exit 0 is `pass`, 1 is `fail`, anything else is `error`.
6. The summary is the last non-empty stdout line, truncated to 2 KB.
7. On `pass`, every declared evidence file must exist or the run is `error`.

This is separation of credentials, not a sandbox (RFC 0003 section 5). When
`user` is set the script runs as that operating-system user, which requires
the API process to be allowed to switch users.
"""

import asyncio
import contextlib
import os
import shutil
import signal
import tempfile
from pathlib import Path

from opengrc.kernel.constraints import timeout_seconds
from opengrc.kernel.timeutil import now
from opengrc.plugins.ports import CollectedFile, RunReport, RunRequest, Secrets

SUMMARY_LIMIT = 2048
DEFAULT_PATH = "/usr/local/bin:/usr/bin:/bin"


def summary_of(stdout: bytes) -> str:
    lines = [line for line in stdout.decode(errors="replace").splitlines() if line.strip()]
    text = lines[-1].strip() if lines else ""
    return text.encode()[:SUMMARY_LIMIT].decode(errors="ignore")


class ShellRunner:
    name = "shell"

    def __init__(
        self, secrets: Secrets, *, user: str | None = None, shell: str = "/bin/sh"
    ) -> None:
        self._secrets = secrets
        self._user = user
        self._shell = shell

    def environment(self, request: RunRequest) -> tuple[dict[str, str], list[str]]:
        test, impl = request.test, request.implementation
        env = {"PATH": DEFAULT_PATH, "HOME": "/nonexistent", "LANG": "C.UTF-8"}
        missing = []
        for name in request.secrets.names:
            value = self._secrets.get(name)
            if value is None:
                missing.append(name)
            else:
                env[name] = value
        for name, value in request.parameters.items():
            env[f"OGRC_PARAM_{name.upper()}"] = value
        env["OGRC_CONTROL_ID"] = test.control_ref
        env["OGRC_TEST_ID"] = test.id
        env["OGRC_IMPLEMENTATION_ID"] = impl.id
        if impl.system_ref:
            env["OGRC_SYSTEM_ID"] = impl.system_ref
        return env, missing

    async def run(self, request: RunRequest) -> RunReport:
        run = request.test.run
        assert run is not None and run.command is not None
        observed = now()
        env, missing = self.environment(request)
        if missing:
            return RunReport("error", f"no configured value for {', '.join(missing)}", observed)
        try:
            limit = timeout_seconds(run.timeout)
        except ValueError as exc:
            return RunReport("error", str(exc), observed)

        scratch = Path(tempfile.mkdtemp(prefix="ogrc-run-"))
        try:
            script = scratch / ".ogrc-command.sh"
            script.write_text(run.command)
            if self._user:
                shutil.chown(scratch, user=self._user)
            process = await asyncio.create_subprocess_exec(
                self._shell,
                str(script),
                cwd=scratch,
                env=env,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
                start_new_session=True,
                user=self._user,
            )
            try:
                stdout, _ = await asyncio.wait_for(process.communicate(), timeout=limit)
            except TimeoutError:
                with contextlib.suppress(ProcessLookupError):
                    os.killpg(process.pid, signal.SIGKILL)
                await process.wait()
                return RunReport("error", f"timed out after {run.timeout or '5m'}", observed)

            code = process.returncode
            outcome = "pass" if code == 0 else "fail" if code == 1 else "error"
            summary = summary_of(stdout) or f"exit status {code}"
            files: list[CollectedFile] = []
            absent: list[str] = []
            for item in run.evidence or []:
                path = (scratch / item.path).resolve()
                if scratch.resolve() not in path.parents or not path.is_file():
                    absent.append(item.path)
                    continue
                files.append(CollectedFile(item.name, item.media_type, path.read_bytes()))
            if outcome == "pass" and absent:
                outcome = "error"
                summary = f"declared evidence is missing: {', '.join(absent)}"
            return RunReport(outcome, summary, observed, files)  # type: ignore[arg-type]
        finally:
            shutil.rmtree(scratch, ignore_errors=True)
