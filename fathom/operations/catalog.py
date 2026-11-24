"""Installed integration packages (RFC 0005 section 4).

Two kinds: packages loaded from a directory at startup (`FATHOM_INTEGRATIONS_DIR`,
which may be a read-only mount), and archive versions installed through the
API. Archive bytes live in object storage. Each process reads an enabled
version into memory the first time it needs it and runs it from there, so
nothing is written to disk and the root filesystem can be read-only. Every
process reads which version is enabled from the store, so they agree.

Fetches go through the BlobStore port; a deployment that wants a shared cache
in front of object storage can wrap that port without touching this module.
"""

import asyncio
import hashlib

from fathom.integrations.archive import read_archive
from fathom.integrations.manifest import Package, PackageError, load_files
from fathom.operations.connections import ConnectionStore, InstallRecord
from fathom.operations.store import BlobStore


class PackageCatalog:
    def __init__(self, store: ConnectionStore, blobs: BlobStore) -> None:
        self._store = store
        self._blobs = blobs
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
        """Read a stored archive into memory and load it."""
        content = await self._blobs.get(record.uri)
        if content is None or hashlib.sha256(content).hexdigest() != record.digest:
            raise PackageError(f"the archive of {record.id} {record.version} is missing or altered")
        files = await asyncio.to_thread(read_archive, content)
        package = await asyncio.to_thread(load_files, files, record.tier)
        if (package.manifest.id, package.manifest.version) != (record.id, record.version):
            raise PackageError(f"the archive of {record.id} {record.version} holds another package")
        # The archive digest, not the manifest's, identifies an installed version.
        return Package(
            package.manifest, None, record.digest, record.tier, package.schemas, package.files
        )
