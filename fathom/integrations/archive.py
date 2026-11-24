"""Reading an integration archive into memory (RFC 0005 section 4), refusing anything unsafe.

Nothing is written to disk: installed packages run from memory, so Fathom works
on a read-only filesystem. Only regular files and directories, relative paths
with no `..`, at most MAX_MEMBERS entries and MAX_BYTES unpacked.
"""

import gzip
import io
import tarfile
from pathlib import PurePosixPath

from fathom.integrations.manifest import PackageError

MAX_ARCHIVE = 64 * 1024 * 1024
MAX_BYTES = 256 * 1024 * 1024
MAX_MEMBERS = 10_000


def read_archive(content: bytes) -> dict[str, bytes]:
    """Every file in the archive, by its relative POSIX path."""
    if len(content) > MAX_ARCHIVE:
        raise PackageError(f"the archive is larger than {MAX_ARCHIVE} bytes")
    try:
        raw = gzip.decompress(content)
    except (OSError, EOFError) as exc:
        raise PackageError("the archive is not gzip") from exc
    if len(raw) > MAX_BYTES + 1024 * MAX_MEMBERS:
        raise PackageError(f"the archive unpacks to more than {MAX_BYTES} bytes")
    try:
        tar = tarfile.open(fileobj=io.BytesIO(raw), mode="r:")  # noqa: SIM115 - closed below
    except tarfile.TarError as exc:
        raise PackageError("the archive is not a tar file") from exc
    files: dict[str, bytes] = {}
    total = 0
    with tar:
        members = tar.getmembers()
        if len(members) > MAX_MEMBERS:
            raise PackageError(f"the archive has more than {MAX_MEMBERS} entries")
        for member in members:
            path = PurePosixPath(member.name)
            if path.is_absolute() or ".." in path.parts or member.name.startswith("\\"):
                raise PackageError(f"unsafe path in archive: {member.name}")
            if member.isdir():
                continue
            if not member.isfile():
                raise PackageError(f"only files and directories are allowed: {member.name}")
            total += member.size
            if total > MAX_BYTES:
                raise PackageError(f"the archive unpacks to more than {MAX_BYTES} bytes")
            source = tar.extractfile(member)
            assert source is not None
            files[path.as_posix().removeprefix("./")] = source.read()
    return files
