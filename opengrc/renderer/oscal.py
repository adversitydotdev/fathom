"""The OSCAL package for one system and one target NIST framework (RFC 0002 section 9).

Six JSON documents in OSCAL 1.2.3 shape: profile, SSP, mapping collection,
component definition, assessment results, and POA&M. UUIDs are derived from
object ids, so rendering the same graph twice produces the same files. The
render is a view; nothing reads it back.
"""

import json
import uuid
from datetime import datetime
from typing import Any

from opengrc.kernel import ids, status
from opengrc.kernel.graph import Graph
from opengrc.kernel.models import (
    FULL_COVERAGE,
    Evidence,
    Exception_,
    Framework,
    Implementation,
    Mapping,
    Requirement,
    Risk,
)
from opengrc.kernel.parameters import control_values, render, requirement_parameter_keys, requirement_value
from opengrc.kernel.timeutil import format_timestamp
from opengrc.plugins.ports import RenderedFile, RenderRequest
from opengrc.renderer.walk import Walk, walk

OSCAL_VERSION = "1.2.3"
NAMESPACE = uuid.UUID("5b0c8f3e-6a3b-4d55-9e0e-0f9c1e6a1d00")
ORIGINATION = {"provider": "inherited", "subservice": "inherited", "shared": "shared",
               "customer": "customer-configured"}
RISK_LEVEL = [
    ["low", "low", "low", "medium", "medium"],
    ["low", "low", "medium", "medium", "high"],
    ["low", "medium", "medium", "high", "high"],
    ["medium", "medium", "high", "high", "critical"],
    ["medium", "high", "high", "critical", "critical"],
]


def uid(*parts: str) -> str:
    return str(uuid.uuid5(NAMESPACE, "|".join(parts)))


def oscal_control_id(requirement: Requirement) -> str:
    """RFC 0002 section 9: `AC-2(1)` is `ac-2.1`; SP 800-171 r3 is prefixed."""
    label = requirement.display_id or ids.split(requirement.id)[1]
    if "800-171" in requirement.framework_ref:
        return f"SP_800_171_{label}"
    return label.lower().replace("(", ".").replace(")", "").replace(" ", "")


def metadata(title: str, at: datetime, version: str = "1.0") -> dict[str, Any]:
    return {
        "title": title,
        "last-modified": format_timestamp(at),
        "version": version,
        "oscal-version": OSCAL_VERSION,
    }


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


class _Package:
    def __init__(self, request: RenderRequest, w: Walk, framework: Framework) -> None:
        self.request = request
        self.w = w
        self.graph: Graph = w.graph
        self.ev: status.Evaluator = w.evaluator
        self.framework = framework
        self.at = w.evaluator.at
        self.controls = {e.control.id: e for e in w.controls}
        self.in_scope = self._in_scope()

    def _in_scope(self) -> dict[str, tuple[Requirement, list[Mapping]]]:
        """Target requirements in the baseline that a baseline control with an implementation maps to."""
        selected: dict[str, tuple[Requirement, list[Mapping]]] = {}
        for requirement_id in self.ev.baseline.requirement_ids:
            requirement = self.graph.requirement(requirement_id)
            if requirement is None or requirement.is_withdrawn or requirement.is_revoked:
                continue
            if requirement.framework_ref != self.framework.id:
                continue
            mappings = [
                m for m in self.graph.mappings_by_target.get(requirement.id, [])
                if m.source_ref in self.controls
                and not self.ev.is_replaced(m)
                and self.controls[m.source_ref].implementations
            ]
            if mappings:
                selected[requirement.id] = (requirement, mappings)
        return selected

    def implementations_by_control(self) -> dict[str, Implementation]:
        return {cid: e.implementations[0] for cid, e in self.controls.items() if e.implementations}

    def parameters(self, requirement: Requirement) -> list[dict[str, Any]]:
        out = []
        for key in requirement_parameter_keys(self.graph, requirement.id):
            value = requirement_value(
                self.graph, requirement.id, key,
                program_controls=self.ev.baseline.control_ids,
                implementations=self.implementations_by_control(),
                bindings=self.ev.baseline.parameter_bindings,
            )
            if value:
                out.append({"param-id": key, "values": [value]})
        return out

    # --- documents ----------------------------------------------------------------------

    def profile(self) -> dict[str, Any]:
        source = self.framework.source or {}
        href = source.get("uri", "")
        if source.get("path"):
            href = f"{href.rstrip('/')}/blob/{source.get('commit', 'main')}/{source['path']}"
        set_params = [p for req, _ in self.in_scope.values() for p in self.parameters(req)]
        doc: dict[str, Any] = {
            "uuid": uid("profile", self.request.program.id, self.framework.id),
            "metadata": metadata(f"{self.request.program.name}: {self.framework.name}", self.at),
            "imports": [{
                "href": href,
                "include-controls": [{"with-ids": sorted(oscal_control_id(r) for r, _ in self.in_scope.values())}],
            }],
        }
        if set_params:
            doc["modify"] = {"set-parameters": set_params}
        return {"profile": doc}

    def ssp(self) -> dict[str, Any]:
        system = self.w.system
        program = self.request.program
        components = [
            {"uuid": uid("component", "this-system", program.system_ref), "type": "this-system",
             "title": "This system", "description": (system.function if system else None) or "This system",
             "status": {"state": "operational"}}
        ]
        for ref in (system.component_refs or []) if system else []:
            component = self.graph.component(ref)
            if component is not None:
                components.append({
                    "uuid": uid("component", component.id), "type": component.kind,
                    "title": component.name, "description": component.description or component.name,
                    "status": {"state": "operational"},
                    "props": [{"name": "opengrc-id", "ns": "https://opengrc.dev/ns", "value": component.id}],
                })
        leveraged = [
            {"uuid": uid("leveraged", p.party_ref), "title": p.function or p.party_ref,
             "party-uuid": uid("party", p.party_ref), "date-authorized": str(p.authorization.authorized),
             "props": [{"name": "authorization-identifier", "ns": "https://opengrc.dev/ns",
                        "value": p.authorization.identifier}]}
            for p in (system.parties or []) if system and p.role == "subservice" and p.authorization
        ]
        info_types = [
            {"uuid": uid("info", program.system_ref, i.name), "title": i.name,
             "description": i.description or i.name,
             "confidentiality-impact": {"base": f"fips-199-{i.confidentiality}"},
             "integrity-impact": {"base": f"fips-199-{i.integrity}"},
             "availability-impact": {"base": f"fips-199-{i.availability}"}}
            for i in (system.information_types or []) if system
        ]
        requirements = []
        for requirement, mappings in self.in_scope.values():
            impls = [i for m in mappings for i in self.controls[m.source_ref].implementations]
            remarks = []
            for m in mappings:
                entry = self.controls[m.source_ref]
                reviews = self.graph.reviews_by_mapping.get(m.id, [])
                review = f"; organization review: {reviews[-1].review_status}" if reviews else ""
                remarks.append(
                    f"{entry.control.display_id or entry.control.id} ({m.relationship}{review}): "
                    f"{entry.statement.strip()}"
                )
                for i in entry.implementations:
                    if i.narrative:
                        remarks.append(f"{i.id}: {i.narrative.strip()}")
                for exc in entry.exceptions:
                    remarks.append(f"Exception until {exc.expires}: {exc.justification.strip()}")
            for finding in self.w.findings:
                if ids.base(finding.objective_ref) == requirement.id:
                    remarks.append(f"Finding {finding.id}: {finding.determination} on {finding.observed}")
            by_component = []
            for i in impls:
                component_uuid = (
                    uid("component", i.component_ref) if i.component_ref
                    else uid("component", "this-system", program.system_ref)
                )
                by_component.append({
                    "component-uuid": component_uuid, "uuid": uid("by-component", requirement.id, i.id),
                    "description": i.narrative or i.id,
                    "implementation-status": {"state": i.status if i.status != "exception" else "partial"},
                })
            statement_ids = sorted({ids.fragment(m.target_ref) for m in mappings if ids.fragment(m.target_ref)})
            control_id = oscal_control_id(requirement)
            item: dict[str, Any] = {
                "uuid": uid("implemented-requirement", program.id, requirement.id),
                "control-id": control_id,
                "props": [{"name": "implementation-status", "value": implementation_status(impls, mappings)}],
                "by-components": by_component,
                "remarks": "\n\n".join(remarks),
            }
            params = self.parameters(requirement)
            if params:
                item["set-parameters"] = params
            if statement_ids:
                item["statements"] = [
                    {"statement-id": f"{control_id}_smt.{s}", "uuid": uid("statement", requirement.id, s)}
                    for s in statement_ids
                ]
            requirements.append(item)
        doc = {
            "uuid": uid("ssp", program.id, self.framework.id),
            "metadata": metadata(f"System security plan: {system.name if system else program.system_ref}", self.at),
            "import-profile": {"href": "profile.json"},
            "system-characteristics": {
                "system-ids": [{"identifier-type": "https://opengrc.dev/ns", "id": program.system_ref}],
                "system-name": system.name if system else program.system_ref,
                "description": (system.function if system else None) or "",
                "system-information": {"information-types": info_types},
                "status": {"state": "operational"},
                "authorization-boundary": {"description": (system.boundary if system else None) or ""},
            },
            "system-implementation": {
                "users": [],
                "components": components,
                **({"leveraged-authorizations": leveraged} if leveraged else {}),
            },
            "control-implementation": {
                "description": f"Implementations for {self.framework.name}.",
                "implemented-requirements": requirements,
            },
        }
        return {"system-security-plan": doc}

    def mapping_collection(self) -> dict[str, Any]:
        maps = []
        for requirement in self.graph.requirements_by_framework.get(self.framework.id, []):
            for m in self.graph.mappings_by_target.get(requirement.id, []):
                if not self.graph.is_library(m.id):
                    continue
                target = oscal_control_id(requirement)
                frag = ids.fragment(m.target_ref)
                props = [{"name": "review-status", "value": m.review_status or "draft"}]
                for review in self.graph.reviews_by_mapping.get(m.id, []):
                    props.append({"name": "mapping-review", "value": review.review_status})
                for key, name in (m.parameter_map or {}).items():
                    props.append({"name": "parameter-map", "value": f"{key}={name}"})
                entry: dict[str, Any] = {
                    "uuid": uid("map", m.id),
                    "relationship": m.relationship,
                    "sources": [{"type": "control", "id-ref": m.source_ref}],
                    "targets": [{"type": "control", "id-ref": f"{target}_smt.{frag}" if frag else target}],
                    "props": props,
                }
                if m.rationale:
                    entry["rationale"] = m.rationale
                if m.confidence:
                    entry["confidence-score"] = {"category": m.confidence}
                maps.append(entry)
        pin = self.graph.library_ids
        return {"mapping-collection": {
            "uuid": uid("mappings", self.framework.id),
            "metadata": metadata(f"OpenGRC mappings to {self.framework.name}", self.at),
            "provenance": {"method": "human", "remarks": f"Generated from the pinned library ({len(pin)} objects)."},
            "mappings": [{"uuid": uid("mapping-set", self.framework.id), "maps": maps}],
        }}

    def component_definition(self) -> dict[str, Any]:
        system = self.w.system
        components = []
        for ref in (system.component_refs or []) if system else []:
            component = self.graph.component(ref)
            if component is None:
                continue
            impls = [i for i in self.graph.implementations if i.component_ref == ref and not i.system_ref]
            reqs = []
            for i in impls:
                targets = [self.graph.requirement(i.requirement_ref)] if i.requirement_ref else [
                    self.graph.requirement(m.target_ref)
                    for m in self.graph.mappings_by_source.get(i.control_ref or "", [])
                ]
                for target in targets:
                    if target is None or target.framework_ref != self.framework.id:
                        continue
                    description = "\n\n".join(x for x in (i.narrative, i.customer_responsibility) if x)
                    reqs.append({
                        "uuid": uid("cd-req", i.id, target.id), "control-id": oscal_control_id(target),
                        "description": description or i.id,
                        "props": [{"name": "control-origination", "value": ORIGINATION[i.responsibility]}],
                    })
            components.append({
                "uuid": uid("component", component.id), "type": component.kind, "title": component.name,
                "description": component.description or component.name,
                "control-implementations": [{
                    "uuid": uid("cd-impl", component.id, self.framework.id),
                    "source": (self.framework.source or {}).get("uri", self.framework.id),
                    "description": f"{component.name} against {self.framework.name}.",
                    "implemented-requirements": reqs,
                }] if reqs else [],
            })
        return {"component-definition": {
            "uuid": uid("component-definition", self.request.program.system_ref),
            "metadata": metadata("Components of the system", self.at),
            "components": components,
        }}

    def _evidence_resources(self, refs: list[str]) -> list[dict[str, Any]]:
        out = []
        for ref in refs:
            e = self.graph.typed(ref, Evidence)
            if e is None or e.resource is None:
                continue
            resource: dict[str, Any] = {"uuid": uid("resource", e.id), "title": e.name}
            if e.resource.uri:
                resource["rlinks"] = [{"href": e.resource.uri, **(
                    {"hashes": [{"algorithm": "SHA-256", "value": e.resource.digest.value}]}
                    if e.resource.digest else {})}]
            out.append(resource)
        return out

    def assessment_results(self) -> dict[str, Any]:
        findings, resources = [], []
        for f in self.w.findings:
            requirement = self.graph.requirement(f.objective_ref)
            if requirement is None or requirement.framework_ref != self.framework.id:
                continue
            target_id = f"{oscal_control_id(requirement)}_obj.{ids.objective_of(f.objective_ref)}"
            entry: dict[str, Any] = {
                "uuid": uid("finding", f.id), "title": f.name, "description": f.narrative,
                "target": {"type": "objective-id", "target-id": target_id,
                           "status": {"state": f.determination}},
            }
            if f.risk_ref:
                entry["related-risks"] = [{"risk-uuid": uid("risk", f.risk_ref)}]
            findings.append(entry)
            resources += self._evidence_resources(f.evidence_refs or [])
        doc: dict[str, Any] = {
            "uuid": uid("assessment-results", self.request.program.id, self.framework.id),
            "metadata": metadata("Assessment results", self.at),
            "import-ap": {"href": "#"},
            "results": [{
                "uuid": uid("result", self.request.program.id, format_timestamp(self.at)),
                "title": "Findings in force", "description": "Findings in force for the system.",
                "start": format_timestamp(self.at), "reviewed-controls": {"control-selections": [{"include-all": {}}]},
                "findings": findings,
            }],
        }
        if resources:
            doc["back-matter"] = {"resources": resources}
        return {"assessment-results": doc}

    def poam(self) -> dict[str, Any]:
        items: list[dict[str, Any]] = []
        risks: list[dict[str, Any]] = []
        mapped = {m.source_ref for _, ms in self.in_scope.values() for m in ms}
        for risk in self.graph.all(Risk):
            if risk.status in ("accepted", "closed") or not risk.milestones:
                continue
            if not mapped & set(risk.control_refs or []):
                continue
            risks.append(self._risk(risk))
            items.append({"uuid": uid("poam-risk", risk.id), "title": risk.name, "description": risk.statement,
                          "related-risks": [{"risk-uuid": uid("risk", risk.id)}]})
        in_scope_impls = {i.id for e in self.controls.values() for i in e.implementations}
        for exc in self.graph.all(Exception_):
            if exc.implementation_ref in in_scope_impls and exc.expires >= self.ev.date:
                items.append({"uuid": uid("poam-exception", exc.id), "title": f"Exception {exc.id}",
                              "description": f"{exc.justification.strip()} Expires {exc.expires}."})
        for f in self.w.findings:
            if f.determination == "not-satisfied":
                item: dict[str, Any] = {"uuid": uid("poam-finding", f.id), "title": f.name,
                                        "description": f.narrative,
                                        "related-findings": [{"finding-uuid": uid("finding", f.id)}]}
                if f.risk_ref:
                    item["related-risks"] = [{"risk-uuid": uid("risk", f.risk_ref)}]
                items.append(item)
        doc: dict[str, Any] = {
            "uuid": uid("poam", self.request.program.id, self.framework.id),
            "metadata": metadata("Plan of action and milestones", self.at),
            "import-ssp": {"href": "ssp.json"},
            "poam-items": items,
        }
        if risks:
            doc["risks"] = risks
        return {"plan-of-action-and-milestones": doc}

    def _risk(self, risk: Risk) -> dict[str, Any]:
        level = RISK_LEVEL[risk.likelihood - 1][risk.impact - 1]
        return {
            "uuid": uid("risk", risk.id), "title": risk.name, "description": risk.statement,
            "statement": risk.statement, "status": risk.status,
            "characterizations": [{"origin": {"actors": [{"type": "party", "actor-uuid": uid("org")}]},
                                   "facets": [
                                       {"name": "likelihood", "system": "https://opengrc.dev/ns", "value": str(risk.likelihood)},
                                       {"name": "impact", "system": "https://opengrc.dev/ns", "value": str(risk.impact)},
                                       {"name": "risk", "system": "https://opengrc.dev/ns", "value": level}]}],
            "remediations": [{"uuid": uid("remediation", risk.id), "lifecycle": "planned",
                              "title": risk.treatment, "description": risk.treatment,
                              "tasks": [{"uuid": uid("task", risk.id, m.name), "type": "milestone",
                                         "title": m.name,
                                         "timing": {"on-date": {"date": f"{m.due}T00:00:00Z"}},
                                         **({"remarks": f"done {m.done}"} if m.done else {})}
                                        for m in risk.milestones or []]}],
        }


class OscalRenderer:
    name = "oscal"

    def render(self, request: RenderRequest) -> list[RenderedFile]:
        framework = request.graph.typed(request.framework_id, Framework)
        if framework is None:
            raise ValueError(f"framework {request.framework_id} is not in the pinned library")
        package = _Package(request, walk(request), framework)
        documents = {
            "profile.json": package.profile(),
            "ssp.json": package.ssp(),
            "mapping-collection.json": package.mapping_collection(),
            "component-definition.json": package.component_definition(),
            "assessment-results.json": package.assessment_results(),
            "poam.json": package.poam(),
        }
        return [
            RenderedFile(name, "application/json", json.dumps(doc, indent=2, sort_keys=False).encode())
            for name, doc in documents.items()
        ]


__all__ = ["OscalRenderer", "control_values", "render"]
