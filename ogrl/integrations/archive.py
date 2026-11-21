"""Unpacking an integration archive (RFC 0005 section 4), refusing anything unsafe.

Only regular files and directories, relative paths with no `..`, at most
MAX_MEMBERS entries and MAX_BYTES unpacked. Executables under `bin/` keep
their execute bit; nothing else does.
"""

import gzip
import io
import tarfile
from pathlib import Path, PurePosixPath

from ogrl.integrations.manifest import PackageError

MAX_ARCHIVE = 64 * 1024 * 1024
MAX_BYTES = 256 * 1024 * 1024
MAX_MEMBERS = 10_000


def unpack(content: bytes, dest: Path) -> Path:
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
    dest.mkdir(parents=True, exist_ok=True)
    root = dest.resolve()
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
                (root / path).mkdir(parents=True, exist_ok=True)
                continue
            if not member.isfile():
                raise PackageError(f"only files and directories are allowed: {member.name}")
            total += member.size
            if total > MAX_BYTES:
                raise PackageError(f"the archive unpacks to more than {MAX_BYTES} bytes")
            target = (root / path).resolve()
            if root not in target.parents:
                raise PackageError(f"unsafe path in archive: {member.name}")
            target.parent.mkdir(parents=True, exist_ok=True)
            source = tar.extractfile(member)
            assert source is not None
            target.write_bytes(source.read())
            target.chmod(0o755 if path.parts[0] == "bin" else 0o644)
    return dest
