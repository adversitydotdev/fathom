"""Bytes are a side route (RFC 0004 section 3).

`POST /{evidence,policies,procedures}/{id}/content` stores the file, sets
`resource.uri`, `resource.media_type`, and `resource.digest`, and returns the
object with a later `modified`. `GET` of the same route returns the bytes.
The object never holds them.
"""

from collections.abc import Callable
from datetime import datetime

from opengrc.access import ActorKind, Authorizer, Principal, require
from opengrc.errors import Conflict, Forbidden, NotFound, UnsupportedMediaType
from opengrc.kernel.bundles import digest
from opengrc.kernel.models import Envelope, Evidence
from opengrc.kernel.timeutil import later_than, now
from opengrc.operations.objects import ObjectService, TypeSpec
from opengrc.operations.store import BlobStore

DOCUMENT_TYPES = frozenset(
    {
        "text/markdown",
        "text/plain",
        "text/html",
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.oasis.opendocument.text",
    }
)
MAX_BYTES = 100 * 1024 * 1024


def accepts(spec: TypeSpec, media_type: str) -> bool:
    base = media_type.split(";", 1)[0].strip().lower()
    if not base or "/" not in base or base.startswith("multipart/"):
        return False
    if spec.type == "evidence":
        return True
    return base in DOCUMENT_TYPES


class ContentService:
    def __init__(
        self,
        objects: ObjectService,
        blobs: BlobStore,
        authorizer: Authorizer,
        clock: Callable[[], datetime] = now,
    ) -> None:
        self._objects = objects
        self._blobs = blobs
        self._authorizer = authorizer
        self._clock = clock

    async def upload(
        self,
        principal: Principal,
        spec: TypeSpec,
        object_id: str,
        if_match: datetime,
        content: bytes,
        media_type: str,
    ) -> Envelope:
        assert spec.write_permission is not None
        require(self._authorizer, principal, spec.write_permission)
        row = await self._objects.editable(spec, object_id, if_match)
        old = row.obj
        if not accepts(spec, media_type):
            raise UnsupportedMediaType(f"{media_type or 'no media type'} is not accepted here")
        if len(content) > MAX_BYTES:
            raise UnsupportedMediaType("the upload is larger than 100 MiB")
        if isinstance(old, Evidence) and old.complete and old.resource and old.resource.digest:
            raise Conflict(
                "this evidence is complete; revoke it and record new evidence",
                slug="evidence-complete",
            )
        if principal.kind is ActorKind.AGENT and getattr(old, "status", None) == "adopted":
            raise Forbidden("an agent does not change an adopted document", slug="agent-refused")
        sha = digest(content)
        uri = await self._blobs.put(f"{spec.type}/{object_id}/{sha}", content, media_type)
        resource = {
            **(old.resource.model_dump(mode="json", exclude_none=True) if old.resource else {}),  # type: ignore[attr-defined]
            "uri": uri,
            "media_type": media_type,
            "digest": {"algorithm": "sha-256", "value": sha},
        }
        updated = spec.model.model_validate(
            {**old.body(), "resource": resource, "modified": later_than(old.modified, self._clock())}
        )
        return await self._objects.replace_as(updated, old, principal.actor_id)

    async def download(
        self, principal: Principal, spec: TypeSpec, object_id: str
    ) -> tuple[bytes, str]:
        obj = await self._objects.get(principal, spec, object_id)
        resource = getattr(obj, "resource", None)
        if resource is None or not resource.uri or resource.digest is None:
            raise NotFound(f"{object_id} has no stored content")
        content = await self._blobs.get(resource.uri)
        if content is None:  # a restore copied the bytes and kept the object's URI
            alias = await self._objects.store.get_meta(f"blob-alias:{resource.uri}")
            content = await self._blobs.get(alias) if alias else None
        if content is None:
            raise NotFound(f"the bytes for {object_id} are not in this deployment's storage")
        return content, resource.media_type or "application/octet-stream"
