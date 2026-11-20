"""The OSCAL package for one system and one target NIST framework (RFC 0002 section 9).

Delegates 6-document OSCAL 1.2.3 rendering (JSON, plus optional XML) to `ogrl_rs`
(`ogrl-oscal`) so CLI and API produce identical deterministic packages.
"""

import ogrl_rs

from ogrl.kernel import ids
from ogrl.kernel.models import FULL_COVERAGE, Framework, Implementation, Mapping, Requirement
from ogrl.plugins.ports import RenderedFile, RenderRequest


def oscal_control_id(requirement: Requirement) -> str:
    """RFC 0002 section 9: `AC-2(1)` is `ac-2.1`; SP 800-171 r3 is prefixed."""
    label = requirement.display_id or ids.split(requirement.id)[1]
    if "800-171" in requirement.framework_ref:
        return f"SP_800_171_{label}"
    return label.lower().replace("(", ".").replace(")", "").replace(" ", "")


def implementation_status(impls: list[Implementation], mappings: list[Mapping]) -> str:
    """The table in RFC 0002 section 9."""
    statuses = {i.status for i in impls}
    if statuses == {"implemented"} and all(m.relationship in FULL_COVERAGE for m in mappings):
        return "implemented"
    if statuses == {"not-applicable"}:
        return "not-applicable"
    if "planned" in statuses and not statuses & {"implemented", "partial"}:
        return "planned"
    return "partial"


class OscalRenderer:
    name = "oscal"

    def __init__(self, *, include_xml: bool = False) -> None:
        self.include_xml = include_xml

    def render(self, request: RenderRequest) -> list[RenderedFile]:
        framework = request.graph.typed(request.framework_id, Framework)
        if framework is None:
            raise ValueError(f"framework {request.framework_id} is not in the pinned library")
        files = ogrl_rs.render_oscal(
            [o.body() for o in request.graph.objects.values()],
            request.program.id,
            framework.id,
            request.at,
            library_ids=request.graph.library_ids,
            provider_ids=request.graph.provider_ids,
            include_xml=self.include_xml,
        )
        return [RenderedFile(f.name, f.media_type, f.content) for f in files]
