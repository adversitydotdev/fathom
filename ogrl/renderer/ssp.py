"""The narrative SSP: a system description plus control matrix (RFC 0001 section 8.1).

Delegates rendering of `ssp.md` and `ssp.json` to `ogrl_rs` (`ogrl-oscal`).
"""

import ogrl_rs

from ogrl.plugins.ports import RenderedFile, RenderRequest


class SspRenderer:
    name = "ssp"

    def render(self, request: RenderRequest) -> list[RenderedFile]:
        files = ogrl_rs.render_ssp(
            [o.body() for o in request.graph.objects.values()],
            request.program.id,
            request.at,
            library_ids=request.graph.library_ids,
            provider_ids=request.graph.provider_ids,
        )
        return [RenderedFile(f.name, f.media_type, f.content) for f in files]
