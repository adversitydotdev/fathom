"""The narrative SSP: a system description plus control matrix (RFC 0001 section 8.1).

Two files: `ssp.md` for a reader, and `ssp.json` with the same walk as data.
"""

import json

from opengrc.plugins.ports import RenderedFile, RenderRequest
from opengrc.renderer.walk import walk


class SspRenderer:
    name = "ssp"

    def render(self, request: RenderRequest) -> list[RenderedFile]:
        w = walk(request)
        system = w.system
        lines = [
            f"# System security plan: {system.name if system else request.program.system_ref}",
            "",
        ]
        lines += [f"Program: {request.program.name} ({request.program.id})"]
        lines += [
            f"Baseline: {request.program.baseline_ref}",
            f"Evaluated at: {w.evaluator.at.isoformat()}",
            "",
        ]
        if system is not None:
            lines += [
                "## System",
                "",
                f"**Function.** {system.function or '—'}",
                "",
                f"**Boundary.** {system.boundary or '—'}",
                "",
            ]
            for info in system.information_types or []:
                lines.append(
                    f"- {info.name}: confidentiality {info.confidentiality}, "
                    f"integrity {info.integrity}, availability {info.availability}"
                )
            components = [w.graph.component(ref) for ref in system.component_refs or []]
            if components:
                lines += ["", "**Components.**", ""]
                lines += [f"- {c.name} ({c.kind})" for c in components if c is not None]
            for party in system.parties or []:
                auth = party.authorization
                suffix = f", authorization {auth.identifier} until {auth.expires}" if auth else ""
                lines.append(f"- Party {party.party_ref}: {party.role}{suffix}")
            lines.append("")
        lines += ["## Controls", ""]
        for entry in w.controls:
            c = entry.control
            lines += [
                f"### {c.display_id or c.id} {c.name}",
                "",
                f"**Status:** {entry.status.state}",
                "",
                entry.statement.strip(),
                "",
            ]
            for impl in entry.implementations:
                where = impl.component_ref or impl.system_ref
                lines += [
                    f"- **{impl.status}**, {impl.responsibility}, on {where}: "
                    f"{(impl.narrative or '').strip()}"
                ]
            for result in entry.latest_results:
                lines.append(
                    f"- Latest result of {result.test_ref}: {result.outcome} "
                    f"at {result.observed.isoformat()}"
                )
            for evidence in entry.evidence:
                lines.append(
                    f"- Evidence {evidence.name}, valid until {evidence.valid_until or 'open'}"
                )
            for exc in entry.exceptions:
                lines.append(f"- Exception until {exc.expires}: {exc.justification.strip()}")
            for failure in entry.status.failed:
                lines.append(f"- Gap: {failure}")
            lines.append("")
        if w.findings:
            lines += ["## Findings in force", ""]
            lines += [f"- {f.objective_ref}: {f.determination} ({f.observed})" for f in w.findings]
            lines.append("")
        if w.policies or w.procedures:
            lines += ["## Policies and procedures", ""]
            lines += [f"- Policy {p.name} {p.version or ''}".rstrip() for p in w.policies]
            lines += [f"- Procedure {p.name}" for p in w.procedures]
            lines.append("")
        if w.risks:
            lines += ["## Open risks", ""]
            for risk in w.risks:
                lines.append(
                    f"- {risk.name}: likelihood {risk.likelihood}, impact {risk.impact}, "
                    f"{risk.treatment}"
                )
                for m in risk.milestones or []:
                    lines.append(
                        f"  - {m.name}, due {m.due}{', done ' + str(m.done) if m.done else ''}"
                    )
        data = {
            "program_id": request.program.id,
            "at": w.evaluator.at.isoformat(),
            "system": system.body() if system else None,
            "controls": [
                {
                    "control_id": e.control.id,
                    "state": e.status.state,
                    "failed": e.status.failed,
                    "statement": e.statement,
                    "implementations": [i.body() for i in e.implementations],
                    "latest_results": [r.body() for r in e.latest_results],
                    "evidence": [x.body() for x in e.evidence],
                    "exceptions": [x.body() for x in e.exceptions],
                }
                for e in w.controls
            ],
            "findings": [f.body() for f in w.findings],
            "policies": [p.body() for p in w.policies],
            "procedures": [p.body() for p in w.procedures],
            "risks": [r.body() for r in w.risks],
        }
        return [
            RenderedFile("ssp.md", "text/markdown", "\n".join(lines).encode()),
            RenderedFile("ssp.json", "application/json", json.dumps(data, indent=2).encode()),
        ]
