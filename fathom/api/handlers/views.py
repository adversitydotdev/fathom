"""Handlers for computed views, content, library, providers, and jobs."""

from datetime import datetime
from typing import Annotated

from fastapi import File, Form, Query, Response, UploadFile

from fathom.api.handlers.objects import IfMatch
from fathom.api.paths import views as v
from fathom.api.registrar import CurrentPrincipal, Registrar
from fathom.container import Container
from fathom.operations import types as t
from fathom.operations.harness import RunRequest
from fathom.operations.jobs import JobQuery
from fathom.operations.library import LibraryPullRequest
from fathom.operations.objects import TypeSpec
from fathom.operations.providers import ProviderImportRequest
from fathom.operations.renders import RenderRequest
from fathom.operations.restore import RestoreRequest

At = Annotated[datetime | None, Query(description="Evaluation time. Defaults to now.")]


def register(registrar: Registrar, c: Container) -> None:
    # --- library ---------------------------------------------------------------------------

    async def get_library(principal: CurrentPrincipal):
        pin = await c.library.pin(principal)
        return pin if pin is not None else {}

    async def pull_library(body: LibraryPullRequest, principal: CurrentPrincipal):
        return await c.library.pull(principal, body)

    registrar.handle(v.GET_LIBRARY, get_library)
    registrar.handle(v.PULL_LIBRARY, pull_library)

    # --- computed views ----------------------------------------------------------------------

    async def effective_baseline(id: str, principal: CurrentPrincipal):
        return await c.status.effective_baseline(principal, id)

    async def system_gaps(id: str, principal: CurrentPrincipal, at: At = None):
        return await c.status.system_gaps(principal, id, at)

    async def program_summary(id: str, principal: CurrentPrincipal, at: At = None):
        return await c.status.program_summary(principal, id, at)

    async def program_status(
        id: str, principal: CurrentPrincipal, at: At = None, framework_id: str | None = None
    ):
        return await c.status.program_status(principal, id, at, framework_id)

    async def program_sprs(id: str, principal: CurrentPrincipal, at: At = None):
        return await c.status.program_sprs(principal, id, at)

    registrar.handle(v.GET_PROGRAM_SPRS, program_sprs)
    registrar.handle(v.GET_EFFECTIVE_BASELINE, effective_baseline)
    registrar.handle(v.LIST_SYSTEM_GAPS, system_gaps)
    registrar.handle(v.GET_PROGRAM_SUMMARY, program_summary)
    registrar.handle(v.GET_PROGRAM_STATUS, program_status)

    # --- jobs that start from an object --------------------------------------------------------

    async def run_test(id: str, body: RunRequest, principal: CurrentPrincipal):
        return await c.harness.run(principal, id, body)

    async def render(id: str, body: RenderRequest, principal: CurrentPrincipal):
        return await c.renders.render(principal, id, body)

    registrar.handle(v.RUN_TEST, run_test)
    registrar.handle(v.CREATE_PROGRAM_RENDER, render)

    # --- content -------------------------------------------------------------------------------

    def content_routes(spec: TypeSpec, get_endpoint, upload_endpoint) -> None:
        async def download(id: str, principal: CurrentPrincipal) -> Response:
            content, media_type = await c.content.download(principal, spec, id)
            return Response(content, media_type=media_type)

        async def upload(
            id: str,
            if_match: IfMatch,
            principal: CurrentPrincipal,
            file: Annotated[UploadFile, File()],
            media_type: Annotated[str | None, Form()] = None,
        ):
            content = await file.read()
            kind = media_type or file.content_type or ""
            return await c.content.upload(principal, spec, id, if_match, content, kind)

        registrar.handle(get_endpoint, download)
        registrar.handle(upload_endpoint, upload)

    content_routes(t.EVIDENCE, v.GET_EVIDENCE_CONTENT, v.UPLOAD_EVIDENCE_CONTENT)
    content_routes(t.POLICY, v.GET_POLICY_CONTENT, v.UPLOAD_POLICY_CONTENT)
    content_routes(t.PROCEDURE, v.GET_PROCEDURE_CONTENT, v.UPLOAD_PROCEDURE_CONTENT)

    # --- providers -----------------------------------------------------------------------------

    async def list_providers(principal: CurrentPrincipal):
        return {"data": await c.providers.list(principal)}

    async def get_provider(id: str, principal: CurrentPrincipal):
        return await c.providers.get(principal, id)

    async def import_provider(body: ProviderImportRequest, principal: CurrentPrincipal):
        return await c.providers.import_bundle(principal, body)

    registrar.handle(v.LIST_PROVIDERS, list_providers)
    registrar.handle(v.GET_PROVIDER, get_provider)
    registrar.handle(v.IMPORT_PROVIDER, import_provider)

    # --- export and restore ----------------------------------------------------------------------

    async def export_git(principal: CurrentPrincipal):
        return await c.exports.export(principal)

    async def restore(body: RestoreRequest, principal: CurrentPrincipal):
        return await c.restore.restore(principal, body)

    registrar.handle(v.EXPORT_GIT, export_git)
    registrar.handle(v.RESTORE, restore)

    # --- jobs ------------------------------------------------------------------------------------

    async def list_jobs(principal: CurrentPrincipal, query: Annotated[JobQuery, Query()]):
        return await c.jobs.list(principal, query)

    async def get_job(id: str, principal: CurrentPrincipal):
        return await c.jobs.get(principal, id)

    async def get_job_file(id: str, filename: str, principal: CurrentPrincipal) -> Response:
        content, media_type = await c.jobs.file(principal, id, filename)
        return Response(
            content,
            media_type=media_type,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    registrar.handle(v.LIST_JOBS, list_jobs)
    registrar.handle(v.GET_JOB, get_job)
    registrar.handle(v.GET_JOB_FILE, get_job_file)
