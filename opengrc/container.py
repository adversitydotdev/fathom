"""Composition root. The one place concrete implementations are chosen.

Everything below this file depends on protocols. Swapping Postgres for
memory, Casbin for the static policy, or adding a runner happens here.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from opengrc.access import Authorizer, StaticPolicy
from opengrc.adapters.fetch import UrlFetcher
from opengrc.adapters.git import GitCli
from opengrc.adapters.library import DirectoryLibrary
from opengrc.adapters.secrets import EnvSecrets
from opengrc.auth import Authenticator
from opengrc.features import Feature, FeatureEvaluator, StaticFeatures
from opengrc.importer import OpenGRCBundleImporter, OscalComponentImporter
from opengrc.kernel.timeutil import now
from opengrc.operations.connectors import ConnectorService
from opengrc.operations.content import ContentService
from opengrc.operations.exports import ExportService, ExportSettings
from opengrc.operations.harness import HarnessService
from opengrc.operations.jobs import Executor, InlineExecutor, JobService
from opengrc.operations.library import LibraryService
from opengrc.operations.objects import ObjectService
from opengrc.operations.providers import ProviderService
from opengrc.operations.renders import RenderService
from opengrc.operations.restore import RestoreService
from opengrc.operations.sources import Fetcher, Git, LibrarySource
from opengrc.operations.status import StatusService
from opengrc.operations.store import BlobStore, ObjectStore
from opengrc.persistence.memory import MemoryBlobs, MemoryStore
from opengrc.plugins import Plugins
from opengrc.plugins.ports import Secrets
from opengrc.renderer import OscalRenderer, SspRenderer
from opengrc.runner import ShellRunner

REPOSITORY_LIBRARY = Path(__file__).resolve().parents[1] / "library"


@dataclass(frozen=True)
class Container:
    version: str
    authenticator: Authenticator
    authorizer: Authorizer
    features: FeatureEvaluator
    store: ObjectStore
    blobs: BlobStore
    objects: ObjectService
    status: StatusService
    content: ContentService
    jobs: JobService
    library: LibraryService
    providers: ProviderService
    harness: HarnessService
    renders: RenderService
    exports: ExportService
    restore: RestoreService
    connectors: ConnectorService
    plugins: Plugins = field(default_factory=Plugins)


def build(
    *,
    authenticator: Authenticator,
    store: ObjectStore | None = None,
    controls: ObjectStore | None = None,
    authorizer: Authorizer | None = None,
    features: FeatureEvaluator | None = None,
    blobs: BlobStore | None = None,
    executor: Executor | None = None,
    library_source: LibrarySource | None = None,
    fetcher: Fetcher | None = None,
    git: Git | None = None,
    secrets: Secrets | None = None,
    export: ExportSettings | None = None,
    harness_user: str | None = None,
    clock: Callable[[], datetime] = now,
    version: str = "0.1.0",
) -> Container:
    """`controls` is the store's older name, kept so existing callers still read well."""
    authorizer = authorizer or StaticPolicy()
    store = store or controls or MemoryStore()
    blobs = blobs or MemoryBlobs()
    fetcher = fetcher or UrlFetcher()
    git = git or GitCli()
    library_source = library_source or DirectoryLibrary(REPOSITORY_LIBRARY)
    export = export or ExportSettings(remote=None)
    if features is None:
        features = StaticFeatures([Feature.GIT_EXPORT] if export.remote else [])

    plugins = Plugins()
    plugins.runners.register("shell", ShellRunner(secrets or EnvSecrets(), user=harness_user))
    plugins.importers.register("opengrc", OpenGRCBundleImporter())
    plugins.importers.register("oscal-component", OscalComponentImporter())
    plugins.renderers.register("ssp", SspRenderer())
    plugins.renderers.register("oscal", OscalRenderer())

    objects = ObjectService(store, authorizer, clock)
    jobs = JobService(store, blobs, authorizer, executor or InlineExecutor(), clock)
    return Container(
        version=version,
        authenticator=authenticator,
        authorizer=authorizer,
        features=features,
        store=store,
        blobs=blobs,
        objects=objects,
        status=StatusService(store, authorizer, clock),
        content=ContentService(objects, blobs, authorizer, clock),
        jobs=jobs,
        library=LibraryService(store, authorizer, jobs, library_source, clock),
        providers=ProviderService(store, authorizer, jobs, fetcher, plugins, clock),
        harness=HarnessService(objects, blobs, authorizer, jobs, plugins, clock),
        renders=RenderService(store, authorizer, jobs, plugins, clock),
        exports=ExportService(store, blobs, authorizer, jobs, git, export, clock),
        restore=RestoreService(store, blobs, authorizer, jobs, library_source, fetcher, git, clock),
        connectors=ConnectorService(objects, blobs, authorizer, jobs, plugins, clock),
        plugins=plugins,
    )
