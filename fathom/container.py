"""Composition root. The one place concrete implementations are chosen.

Everything below this file depends on protocols. Swapping Postgres for
memory, Casbin for the static policy, or adding a runner happens here.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

from fathom.access import Authorizer, Role, StaticPolicy
from fathom.adapters.fetch import UrlFetcher
from fathom.adapters.git import GitCli
from fathom.adapters.library import DirectoryLibrary, GitLibrary
from fathom.adapters.oauth import HttpOAuthClient
from fathom.adapters.queue import JobQueue
from fathom.adapters.secrets import EnvSecrets, MemoryVault
from fathom.adapters.sts import StsRoleAssumer
from fathom.agent.config import AgentConfig
from fathom.auth import Authenticator
from fathom.auth.oidc import IdentityProvider
from fathom.auth.store import AuthStore, MemoryAuthStore
from fathom.features import Feature, FeatureEvaluator, StaticFeatures
from fathom.importer import OGRLBundleImporter, OscalComponentImporter
from fathom.integrations.host import SubprocessHost
from fathom.integrations.manifest import discover
from fathom.kernel.timeutil import now
from fathom.operations.auth import AuthService
from fathom.operations.catalog import PackageCatalog
from fathom.operations.connections import ConnectionStore
from fathom.operations.content import ContentService
from fathom.operations.exports import ExportService, ExportSettings
from fathom.operations.harness import HarnessService
from fathom.operations.integrations import SNAPSHOT_REUSE, IntegrationService
from fathom.operations.jobs import Executor, InlineExecutor, JobService
from fathom.operations.library import LibraryService
from fathom.operations.objects import ObjectService
from fathom.operations.providers import ProviderService
from fathom.operations.renders import RenderService
from fathom.operations.restore import RestoreService
from fathom.operations.schedule import IntegrationScheduler
from fathom.operations.sources import Fetcher, Git, LibrarySource
from fathom.operations.status import StatusService
from fathom.operations.store import BlobStore, ObjectStore
from fathom.persistence.memory import MemoryBlobs, MemoryConnections, MemoryStore
from fathom.plugins import Plugins
from fathom.plugins.ports import IntegrationHost, OAuthClient, RoleAssumer, Secrets, SecretVault
from fathom.renderer import OscalRenderer, SspRenderer
from fathom.runner import ShellRunner

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
    auth_store: AuthStore
    auth: AuthService
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
    integrations: IntegrationService
    scheduler: IntegrationScheduler
    plugins: Plugins = field(default_factory=Plugins)
    queue: JobQueue | None = None
    allowed_origins: tuple[str, ...] = ()
    agent_config: AgentConfig = field(default_factory=AgentConfig)


def build(
    *,
    authenticator: Authenticator,
    store: ObjectStore | None = None,
    controls: ObjectStore | None = None,
    authorizer: Authorizer | None = None,
    features: FeatureEvaluator | None = None,
    blobs: BlobStore | None = None,
    auth_store: AuthStore | None = None,
    oidc_providers: Mapping[str, IdentityProvider] | None = None,
    bootstrap_admin_emails: frozenset[str] = frozenset(),
    default_oidc_roles: tuple[Role, ...] = (Role.VIEWER,),
    executor: Executor | None = None,
    queue: JobQueue | None = None,
    library_source: LibrarySource | None = None,
    fetcher: Fetcher | None = None,
    git: Git | None = None,
    secrets: Secrets | None = None,
    connections: ConnectionStore | None = None,
    vault: SecretVault | None = None,
    integration_host: IntegrationHost | None = None,
    integrations_dir: Path | None = None,
    snapshot_reuse: timedelta = SNAPSHOT_REUSE,
    oauth_client: OAuthClient | None = None,
    role_assumer: RoleAssumer | None = None,
    public_url: str | None = None,
    allow_local_integrations: bool = False,
    export: ExportSettings | None = None,
    harness_user: str | None = None,
    allowed_origins: tuple[str, ...] = (),
    agent_config: AgentConfig | None = None,
    clock: Callable[[], datetime] = now,
    version: str = "0.1.0",
) -> Container:
    """`controls` is the store's older name, kept so existing callers still read well."""
    authorizer = authorizer or StaticPolicy()
    store = store or controls or MemoryStore()
    blobs = blobs or MemoryBlobs()
    auth_store = auth_store or MemoryAuthStore(clock=clock)
    fetcher = fetcher or UrlFetcher()
    git = git or GitCli()
    library_source = library_source or default_library_source()
    export = export or ExportSettings(remote=None)
    if features is None:
        features = StaticFeatures([Feature.GIT_EXPORT] if export.remote else [])

    connections = connections or MemoryConnections()
    catalog = PackageCatalog(connections, blobs)
    plugins = Plugins(integrations=catalog)
    plugins.runners.register("shell", ShellRunner(secrets or EnvSecrets(), user=harness_user))
    plugins.importers.register("ogrl", OGRLBundleImporter())
    plugins.importers.register("oscal-component", OscalComponentImporter())
    plugins.renderers.register("ssp", SspRenderer())
    plugins.renderers.register("oscal", OscalRenderer())
    for package in discover(integrations_dir) if integrations_dir else []:
        plugins.integrations.register(package.id, package)

    objects = ObjectService(store, authorizer, clock)
    jobs = JobService(store, blobs, authorizer, executor or InlineExecutor(), clock)
    integrations = IntegrationService(
        objects,
        blobs,
        authorizer,
        jobs,
        connections,
        vault or MemoryVault(),
        integration_host or SubprocessHost(user=harness_user),
        plugins.integrations,
        clock,
        reuse=snapshot_reuse,
        oauth=oauth_client or HttpOAuthClient(),
        assumer=role_assumer or StsRoleAssumer(),
        public_url=public_url,
        fetcher=fetcher,
        allow_local=allow_local_integrations,
    )
    harness = HarnessService(objects, blobs, authorizer, jobs, plugins, clock, integrations)
    auth = AuthService(
        store,
        auth_store,
        authorizer,
        providers=oidc_providers,
        default_roles=default_oidc_roles,
        bootstrap_admin_emails=bootstrap_admin_emails,
        clock=clock,
    )
    return Container(
        version=version,
        authenticator=authenticator,
        authorizer=authorizer,
        features=features,
        store=store,
        blobs=blobs,
        auth_store=auth_store,
        auth=auth,
        objects=objects,
        status=StatusService(store, authorizer, clock),
        content=ContentService(objects, blobs, authorizer, clock),
        jobs=jobs,
        library=LibraryService(store, authorizer, jobs, library_source, clock),
        providers=ProviderService(store, authorizer, jobs, fetcher, plugins, clock),
        harness=harness,
        renders=RenderService(store, authorizer, jobs, plugins, clock),
        exports=ExportService(store, blobs, authorizer, jobs, git, export, clock, connections),
        restore=RestoreService(
            store, blobs, authorizer, jobs, library_source, fetcher, git, clock, connections
        ),
        integrations=integrations,
        scheduler=IntegrationScheduler(store, connections, integrations, harness, clock),
        plugins=plugins,
        queue=queue,
        allowed_origins=allowed_origins,
        agent_config=agent_config or AgentConfig(),
    )
