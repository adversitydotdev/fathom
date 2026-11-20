"""Composition root. The one place concrete implementations are chosen.

Everything below this file depends on protocols. Swapping Postgres for
memory, Casbin for the static policy, or adding a runner happens here.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from ogrl.access import Authorizer, StaticPolicy
from ogrl.adapters.fetch import UrlFetcher
from ogrl.adapters.git import GitCli
from ogrl.adapters.library import DirectoryLibrary, GitLibrary
from ogrl.adapters.secrets import EnvSecrets
from ogrl.auth import Authenticator
from ogrl.features import Feature, FeatureEvaluator, StaticFeatures
from ogrl.importer import OGRLBundleImporter, OscalComponentImporter
from ogrl.kernel.timeutil import now
from ogrl.operations.connectors import ConnectorService
from ogrl.operations.content import ContentService
from ogrl.operations.exports import ExportService, ExportSettings
from ogrl.operations.harness import HarnessService
from ogrl.operations.jobs import Executor, InlineExecutor, JobService
from ogrl.operations.library import LibraryService
from ogrl.operations.objects import ObjectService
from ogrl.operations.providers import ProviderService
from ogrl.operations.renders import RenderService
from ogrl.operations.restore import RestoreService
from ogrl.operations.sources import Fetcher, Git, LibrarySource
from ogrl.operations.status import StatusService
from ogrl.operations.store import BlobStore, ObjectStore
from ogrl.persistence.memory import MemoryBlobs, MemoryStore
from ogrl.plugins import Plugins
from ogrl.plugins.ports import Secrets
from ogrl.renderer import OscalRenderer, SspRenderer
from ogrl.runner import ShellRunner

DEFAULT_LIBRARY_REPO = "https://github.com/adversitydotdev/ogrl-library"
REPOSITORY_LIBRARY = Path(__file__).resolve().parents[1] / "library"
SIBLING_LIBRARY = Path(__file__).resolve().parents[2] / "ogrl-library" / "library"


def default_library_source() -> LibrarySource:
    if (REPOSITORY_LIBRARY / "bundle.yaml").is_file():
        return DirectoryLibrary(REPOSITORY_LIBRARY)
    if (SIBLING_LIBRARY / "bundle.yaml").is_file():
        return DirectoryLibrary(SIBLING_LIBRARY)
    return GitLibrary(DEFAULT_LIBRARY_REPO)


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
    library_source = library_source or default_library_source()
    export = export or ExportSettings(remote=None)
    if features is None:
        features = StaticFeatures([Feature.GIT_EXPORT] if export.remote else [])

    plugins = Plugins()
    plugins.runners.register("shell", ShellRunner(secrets or EnvSecrets(), user=harness_user))
    plugins.importers.register("ogrl", OGRLBundleImporter())
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
