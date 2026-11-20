"""An OSCAL component definition, imported as provider objects (RFC 0002 section 7).

Delegates JSON and XML OSCAL 1.2.3 parsing and control-origination mapping to
`ogrl_rs` (`ogrl-oscal`) so CLI and API produce byte-identical provider bundles.
"""

from typing import Any

import ogrl_rs

from ogrl.kernel.graph import Graph
from ogrl.kernel.models import parse
from ogrl.plugins.ports import ImportedBundle


def _props(item: dict[str, Any]) -> dict[str, str]:
    return {p.get("name", ""): str(p.get("value", "")) for p in item.get("props", []) or []}


def responsibility(item: dict[str, Any]) -> str:
    """The table in RFC 0002 section 7. The first match wins; anything else is shared."""
    props = _props(item)
    origination = props.get("control-origination", "")
    if props.get("provider", "").lower() == "no" or origination in (
        "customer-configured",
        "customer-provided",
    ):
        return "customer"
    if origination in ("inherited", "service-provider-corporate", "service-provider-system"):
        return "provider"
    return "shared"


def requirement_id(control_id: str, framework: str) -> str:
    """`ac-3` -> requirement--nist-sp-800-53-r5-ac-3; `ac-2.1` -> ...-ac-2-1."""
    slug = control_id.lower()
    slug = slug.removeprefix("sp_800_171_").replace("_", "-").replace(".", "-")
    return f"requirement--{framework}-{slug}"


class OscalComponentImporter:
    name = "oscal-component"

    def import_bytes(self, content: bytes, graph: Graph) -> ImportedBundle:
        rs_graph = ogrl_rs.OgrlGraph.from_objects(
            [o.body() for o in graph.objects.values()],
            library_ids=graph.library_ids,
            provider_ids=graph.provider_ids,
        )
        result = rs_graph.import_oscal_component(content)
        manifest = result["manifest"]
        return ImportedBundle(
            id=manifest["id"],
            name=manifest.get("name"),
            version=str(manifest.get("version") or ""),
            objects=[parse(obj) for obj in result.get("objects", [])],
            warnings=list(result.get("warnings", [])),
        )
