"""Installed integration packages (RFC 0005 section 4).

Two kinds: packages loaded from a local directory at startup, and archive
versions installed through the API. Archive bytes live in object storage;
each process unpacks an enabled version into a cache keyed by its digest the
first time it needs it, so a replaced Fargate task re-fetches on demand and
two processes agree on which version is enabled by reading the store.
"""

import asyncio
import hashlib
import shutil
import tempfile
from pathlib import Path

from ogrl.integrations.archive import unpack
from ogrl.integrations.manifest import Package, PackageError, load_package
from ogrl.operations.connections import ConnectionStore, InstallRecord
from ogrl.operations.store import BlobStore

DEFAULT_CACHE = Path(tempfile.gettempdir()) / "ogrl-integrations"


class PackageCatalog:
    def __init__(
        self, store: ConnectionStore, blobs: BlobStore, cache_dir: Path = DEFAULT_CACHE
    ) -> None:
        self._store = store
        self._blobs = blobs
        self._cache = cache_dir
        self._static: dict[str, Package] = {}
        self._installed: dict[str, Package] = {}
        self._lock = asyncio.Lock()

    # The Registry surface the rest of the application uses.

    def register(self, name: str, package: Package) -> None:
        if name in self._static:
            raise ValueError(f"integration {name!r} is already registered")
        self._static[name] = package

    def get(self, name: str) -> Package | None:
        return self._static.get(name) or self._installed.get(name)

    def names(self) -> list[str]:
        return sorted({*self._static, *self._installed})

    def is_static(self, name: str) -> bool:
        return name in self._static

    async def sync(self) -> None:
        """Make the loaded packages match the enabled versions in the store."""
        async with self._lock:
            enabled = {r.id: r for r in await self._store.list_installs() if r.enabled}
            for integration_id in list(self._installed):
                if integration_id not in enabled:
                    del self._installed[integration_id]
            for integration_id, record in enabled.items():
                current = self._installed.get(integration_id)
                if current is None or current.digest != record.digest:
                    self._installed[integration_id] = await self.load(record)

    async def load(self, record: InstallRecord) -> Package:
        """Unpack a stored archive into the cache (once per digest) and load it."""
        target = self._cache / record.digest
        if not (target / "manifest.yaml").is_file():
            content = await self._blobs.get(record.uri)
            if content is None or hashlib.sha256(content).hexdigest() != record.digest:
                raise PackageError(
                    f"the archive of {record.id} {record.version} is missing or altered"
                )
            await asyncio.to_thread(self._install_into_cache, content, target)
        package = await asyncio.to_thread(load_package, target, record.tier)
        if (package.manifest.id, package.manifest.version) != (record.id, record.version):
            raise PackageError(f"the archive of {record.id} {record.version} holds another package")
        # The archive digest, not the manifest's, identifies an installed version.
        return Package(package.manifest, package.root, record.digest, record.tier, package.schemas)

    def _install_into_cache(self, content: bytes, target: Path) -> None:
        """Unpack beside the target, then rename, so a reader never sees half a package."""
        self._cache.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(dir=self._cache, prefix=".unpack-"))
        try:
            unpack(content, staging)
            shutil.rmtree(target, ignore_errors=True)
            staging.rename(target)
        finally:
            shutil.rmtree(staging, ignore_errors=True)
