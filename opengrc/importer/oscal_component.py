"""An OSCAL component definition, imported as provider objects (RFC 0002 section 7).

The component's title and description become the component. Each party
becomes a party. Each implemented requirement becomes an implementation with
`requirement_ref` resolved from the OSCAL `control-id` against the pinned
catalog, and its description becomes `narrative`. Ids come from the OSCAL
uuids, so a second import of the same document replaces the same rows.
"""

import json
import re
from datetime import UTC, datetime
from typing import Any

from opengrc.kernel.graph import Graph
from opengrc.kernel.models import Component, Envelope, Implementation, Party, Requirement
from opengrc.plugins.ports import ImportedBundle

KINDS = {
    "software": "software",
    "service": "service",
    "hardware": "infrastructure",
    "interconnection": "infrastructure",
    "policy": "procedure",
    "process": "procedure",
    "procedure": "procedure",
    "plan": "procedure",
    "guidance": "procedure",
    "standard": "procedure",
    "validation": "procedure",
    "this-system": "infrastructure",
}
PARTY_KINDS = {"person": "person", "organization": "organization"}
UUID = re.compile(r"^[0-9a-fA-F-]{36}$")


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


def catalog_of(source: str, graph: Graph) -> str | None:
    """Which pinned framework a control-implementation's `source` names."""
    text = source.lower().replace("_", "-")
    if "800-171" in text:
        return "nist-sp-800-171-r3"
    if "800-53" in text:
        return "nist-sp-800-53-r5"
    return None


def requirement_id(control_id: str, framework: str) -> str:
    """`ac-3` -> requirement--nist-sp-800-53-r5-ac-3; `ac-2.1` -> ...-ac-2-1."""
    slug = control_id.lower()
    slug = slug.removeprefix("sp_800_171_").replace("_", "-").replace(".", "-")
    return f"requirement--{framework}-{slug}"


def _timestamp(text: str | None) -> datetime:
    if text:
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
        except ValueError:
            pass
    return datetime(1970, 1, 1, tzinfo=UTC)


class OscalComponentImporter:
    name = "oscal-component"

    def import_bytes(self, content: bytes, graph: Graph) -> ImportedBundle:
        try:
            document = json.loads(content)
        except ValueError as exc:
            raise ValueError("an OSCAL component definition is read as JSON") from exc
        definition = document.get("component-definition")
        if not isinstance(definition, dict) or not UUID.match(str(definition.get("uuid", ""))):
            raise ValueError("the document has no component-definition with a uuid")
        metadata = definition.get("metadata", {})
        stamp = _timestamp(metadata.get("last-modified"))
        envelope = {"created": stamp, "modified": stamp}
        objects: list[Envelope] = []
        warnings: list[str] = []

        for party in metadata.get("parties", []) or []:
            objects.append(
                Party(
                    id=f"party--{party['uuid'].lower()}",
                    name=party.get("name") or party.get("short-name") or party["uuid"],
                    kind=PARTY_KINDS.get(party.get("type", ""), "organization"),
                    **envelope,
                )
            )

        for component in definition.get("components", []) or []:
            component_id = f"component--{component['uuid'].lower()}"
            responsible = [
                f"party--{uuid.lower()}"
                for role in component.get("responsible-roles", []) or []
                for uuid in role.get("party-uuids", []) or []
            ]
            objects.append(
                Component(
                    id=component_id,
                    name=component.get("title") or component["uuid"],
                    kind=KINDS.get(component.get("type", ""), "software"),
                    description=component.get("description"),
                    party_ref=responsible[0] if responsible else None,
                    **envelope,
                )
            )
            for block in component.get("control-implementations", []) or []:
                framework = catalog_of(block.get("source", ""), graph)
                if framework is None:
                    warnings.append(f"{block.get('source')}: not a pinned catalog; skipped")
                    continue
                for item in block.get("implemented-requirements", []) or []:
                    ref = requirement_id(item.get("control-id", ""), framework)
                    if graph.typed(ref, Requirement) is None:
                        warnings.append(
                            f"{item.get('control-id')}: {ref} is not in the pinned library"
                        )
                        continue
                    objects.append(
                        Implementation(
                            id=f"implementation--{item['uuid'].lower()}",
                            origin="provider",
                            component_ref=component_id,
                            requirement_ref=ref,
                            status="implemented",
                            responsibility=responsibility(item),  # type: ignore[arg-type]
                            narrative=item.get("description"),
                            **envelope,
                        )
                    )

        return ImportedBundle(
            id=f"bundle--{definition['uuid'].lower()}",
            name=metadata.get("title"),
            version=str(metadata.get("version") or ""),
            objects=objects,
            warnings=warnings,
        )
