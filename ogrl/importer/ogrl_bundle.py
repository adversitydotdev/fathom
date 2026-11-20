"""A provider bundle authored as OGRL YAML or JSON (RFC 0002 section 7)."""

from ogrl.kernel.bundles import BundleError, read_exchange
from ogrl.kernel.graph import Graph
from ogrl.kernel.models import Implementation
from ogrl.plugins.ports import ImportedBundle


class OGRLBundleImporter:
    name = "ogrl"

    def import_bytes(self, content: bytes, graph: Graph) -> ImportedBundle:
        try:
            manifest, objects = read_exchange(content)
        except BundleError as exc:
            raise ValueError(str(exc)) from exc
        bundle_id = manifest.get("id")
        if not isinstance(bundle_id, str) or not bundle_id.startswith("bundle--"):
            raise ValueError("the manifest id is bundle--<remainder>")
        library = manifest.get("library") or {}
        stamped = []
        for obj in objects:
            if isinstance(obj, Implementation):
                if obj.origin not in (None, "provider"):
                    raise ValueError(
                        f"{obj.id}: a provider bundle's implementations are provider rows"
                    )
                obj = obj.model_copy(update={"origin": "provider"})
                if obj.responsibility in ("shared", "customer") and not obj.customer_responsibility:
                    raise ValueError(
                        f"{obj.id}: a shared or customer row includes customer_responsibility"
                    )
            stamped.append(obj)
        return ImportedBundle(
            id=bundle_id,
            name=manifest.get("name"),
            version=str(manifest.get("version") or ""),
            objects=stamped,
            library_version=library.get("version") if isinstance(library, dict) else None,
        )
