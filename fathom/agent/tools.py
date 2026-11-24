"""Typed Pydantic AI tools wrapping Fathom application services (RFC 0003 §4)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic_ai import Agent, RunContext

from fathom.agent.deps import AgentDeps
from fathom.errors import FathomError
from fathom.operations import types as t
from fathom.operations.integrations import (
    DryRunRequest,
    QueryWrite,
    RulePreviewRequest,
)
from fathom.operations.pagination import PageRequest

SAMPLE_ITEMS = 20  # items a dry run or preview hands back to the model


def register_tools(agent: Agent[AgentDeps, str]) -> None:
    """Register read and draft-only write tools onto a Pydantic AI agent."""

    # --- Read tools -----------------------------------------------------------

    @agent.tool
    async def list_programs(ctx: RunContext[AgentDeps]) -> list[dict[str, Any]]:
        """List compliance programs in the organization."""
        page = await ctx.deps.container.objects.list(
            ctx.deps.principal, t.PROGRAM, PageRequest(limit=50)
        )
        return [
            {
                "id": p.id,
                "name": p.name,
                "system_ref": p.system_ref,
                "baseline_ref": p.baseline_ref,
            }
            for p in page.data
        ]

    @agent.tool
    async def list_controls(ctx: RunContext[AgentDeps], limit: int = 50) -> list[dict[str, Any]]:
        """List controls in the pinned library and organization catalog."""
        page = await ctx.deps.container.objects.list(
            ctx.deps.principal, t.CONTROL, PageRequest(limit=limit)
        )
        return [
            {
                "id": c.id,
                "display_id": c.display_id,
                "name": c.name,
                "family": c.family,
                "statement": c.statement,
                "parameters": getattr(c, "parameters", None),
            }
            for c in page.data
        ]

    @agent.tool
    async def get_control_detail(
        ctx: RunContext[AgentDeps], control_id: str, system_id: str | None = None
    ) -> dict[str, Any]:
        """Inspect one control, its parameters, current implementations, tests, and mappings."""
        ctrl = await ctx.deps.container.objects.get(ctx.deps.principal, t.CONTROL, control_id)
        impls = await ctx.deps.container.objects.list(
            ctx.deps.principal,
            t.IMPLEMENTATION,
            t.ImplementationQuery(control_id=control_id, system_id=system_id, limit=20),
        )
        tests = await ctx.deps.container.objects.list(
            ctx.deps.principal,
            t.TEST,
            t.TestQuery(control_id=control_id, limit=20),
        )
        mappings = await ctx.deps.container.objects.list(
            ctx.deps.principal,
            t.MAPPING,
            t.MappingQuery(source_id=control_id, limit=50),
        )
        return {
            "control": ctrl.body(),
            "implementations": [i.body() for i in impls.data],
            "tests": [x.body() for x in tests.data],
            "mappings": [m.body() for m in mappings.data],
        }

    @agent.tool
    async def get_program_status(
        ctx: RunContext[AgentDeps], program_id: str, at: datetime | None = None
    ) -> dict[str, Any]:
        """Read RFC 0001 §8 computed program status without recomputing it independently."""
        result = await ctx.deps.container.status.program_status(
            ctx.deps.principal, program_id, at=at
        )
        return result.model_dump(mode="json")

    @agent.tool
    async def get_system_gaps(
        ctx: RunContext[AgentDeps], system_id: str, at: datetime | None = None
    ) -> dict[str, Any]:
        """List controls currently in `gap` for every program on a system."""
        gaps = await ctx.deps.container.status.system_gaps(ctx.deps.principal, system_id, at=at)
        return gaps.model_dump(mode="json")

    @agent.tool
    async def list_risks(
        ctx: RunContext[AgentDeps], system_id: str | None = None
    ) -> list[dict[str, Any]]:
        """List open and tracked risks for a system."""
        page = await ctx.deps.container.objects.list(
            ctx.deps.principal, t.RISK, t.RiskQuery(system_id=system_id, limit=50)
        )
        return [r.body() for r in page.data]

    @agent.tool
    async def list_policies(ctx: RunContext[AgentDeps]) -> list[dict[str, Any]]:
        """List adopted and draft policies in the organization."""
        page = await ctx.deps.container.objects.list(
            ctx.deps.principal, t.POLICY, t.PolicyQuery(limit=50)
        )
        return [p.body() for p in page.data]

    @agent.tool
    async def list_findings(
        ctx: RunContext[AgentDeps], system_id: str | None = None
    ) -> list[dict[str, Any]]:
        """List assessment findings on a system."""
        page = await ctx.deps.container.objects.list(
            ctx.deps.principal, t.FINDING, t.FindingQuery(system_id=system_id, limit=50)
        )
        return [f.body() for f in page.data]

    # --- Draft-only write tools (enforced by ObjectService write gates) -------

    @agent.tool
    async def draft_implementation(
        ctx: RunContext[AgentDeps],
        system_ref: str,
        control_ref: str,
        narrative: str,
        responsibility: str = "provider",
        parameter_values: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Draft an implementation narrative with `status: planned` for human review.

        If a `planned` implementation already exists for this system and control,
        updates its narrative/parameters; never modifies human-attested `implemented`
        implementations.
        """
        existing_page = await ctx.deps.container.objects.list(
            ctx.deps.principal,
            t.IMPLEMENTATION,
            t.ImplementationQuery(system_id=system_ref, control_id=control_ref, limit=5),
        )
        existing = next(
            (i for i in existing_page.data if not getattr(i, "component_ref", None)),
            None,
        )
        body: dict[str, Any] = {
            "status": "planned",
            "responsibility": responsibility,
            "narrative": narrative,
        }
        if parameter_values:
            body["parameter_values"] = parameter_values

        if existing is not None:
            if existing.status != "planned":
                return {
                    "skipped": True,
                    "reason": (
                        f"Existing implementation {existing.id} has status '{existing.status}'. "
                        "Agents only edit `planned` drafts; suggest edits to the human instead."
                    ),
                }
            saved = await ctx.deps.container.objects.update(
                ctx.deps.principal, t.IMPLEMENTATION, existing.id, body, existing.modified
            )
        else:
            saved = await ctx.deps.container.objects.create(
                ctx.deps.principal,
                t.IMPLEMENTATION,
                {"system_ref": system_ref, "control_ref": control_ref, **body},
            )

        ctx.deps.created_drafts.append(
            {
                "object_type": "implementation",
                "id": saved.id,
                "control_ref": control_ref,
                "label": f"Draft implementation for {control_ref.replace('control--', '')}",
            }
        )
        return saved.body()

    @agent.tool
    async def draft_policy(
        ctx: RunContext[AgentDeps],
        name: str,
        markdown_body: str,
        version: str = "0.1",
        review_interval: str = "annual",
        control_refs: list[str] | None = None,
    ) -> dict[str, Any]:
        """Create a `draft` policy and store its Markdown body in S3 for human review."""
        payload: dict[str, Any] = {
            "name": name,
            "status": "draft",
            "version": version,
            "review_interval": review_interval,
        }
        if control_refs:
            payload["control_refs"] = control_refs
        created = await ctx.deps.container.objects.create(ctx.deps.principal, t.POLICY, payload)
        uploaded = await ctx.deps.container.content.upload(
            ctx.deps.principal,
            t.POLICY,
            created.id,
            created.modified,
            markdown_body.encode("utf-8"),
            "text/markdown",
        )
        ctx.deps.created_drafts.append(
            {
                "object_type": "policy",
                "id": uploaded.id,
                "label": f"Draft policy: {name}",
            }
        )
        return uploaded.body()

    @agent.tool
    async def draft_risk(
        ctx: RunContext[AgentDeps],
        system_ref: str,
        name: str,
        statement: str,
        likelihood: int = 3,
        impact: int = 3,
        treatment: str = "mitigate",
        control_refs: list[str] | None = None,
    ) -> dict[str, Any]:
        """Record an `open` risk entry for human review (agents cannot mark risks `accepted`)."""
        payload: dict[str, Any] = {
            "system_ref": system_ref,
            "name": name,
            "statement": statement,
            "likelihood": max(1, min(5, likelihood)),
            "impact": max(1, min(5, impact)),
            "treatment": treatment,
            "status": "open",
        }
        if control_refs:
            payload["control_refs"] = control_refs
        created = await ctx.deps.container.objects.create(ctx.deps.principal, t.RISK, payload)
        ctx.deps.created_drafts.append(
            {
                "object_type": "risk",
                "id": created.id,
                "label": f"Draft risk: {name}",
            }
        )
        return created.body()

    @agent.tool
    async def propose_mapping(
        ctx: RunContext[AgentDeps],
        source_ref: str,
        target_ref: str,
        relationship: str,
        summary: str,
        rationale: str = "functional",
        confidence: str = "medium",
    ) -> dict[str, Any]:
        """Propose a crosswalk mapping with `review_status: draft` for human review."""
        body: dict[str, Any] = {
            "source_ref": source_ref,
            "target_ref": target_ref,
            "relationship": relationship,
            "rationale": rationale,
            "review_status": "draft",
            "confidence": confidence,
            "summary": summary,
        }
        created = await ctx.deps.container.objects.create(ctx.deps.principal, t.MAPPING, body)
        ctx.deps.created_drafts.append(
            {
                "object_type": "mapping",
                "id": created.id,
                "control_ref": source_ref if source_ref.startswith("control--") else "",
                "label": f"Draft mapping: {source_ref} → {target_ref}",
            }
        )
        return created.body()

    # --- Query sources (RFC 0006 section 9) ----------------------------------------
    # The agent may search, describe, validate, sample, and preview, but cannot save a
    # query definition or a test with a run block (tests:define-run). It proposes a
    # draft that opens in the query editor, where a person reviews and saves it.

    @agent.tool
    async def list_integrations(ctx: RunContext[AgentDeps]) -> dict[str, Any]:
        """Installed integrations, what each collects, its query model, and its connections."""
        service = ctx.deps.container.integrations
        integrations = await service.list_integrations(ctx.deps.principal)
        connections = await service.list_connections(ctx.deps.principal)
        return {
            "integrations": [
                {
                    "id": i.id,
                    "name": i.name,
                    "query_model": i.query_model,
                    "resources": [
                        {"source": r["source"], "fields": [f["name"] for f in r["fields"]]}
                        for r in i.resources
                    ],
                    "query_sources": [q["source"] for q in i.queries],
                }
                for i in integrations
            ],
            "connections": [
                {"id": c.id, "name": c.name, "integration_id": c.integration_id, "state": c.state}
                for c in connections
            ],
        }

    @agent.tool
    async def search_operations(
        ctx: RunContext[AgentDeps], integration_id: str, text: str
    ) -> list[dict[str, Any]]:
        """Read operations in an integration's API model whose name, path, or summary match."""
        try:
            found = await ctx.deps.container.integrations.search_operations(
                ctx.deps.principal, integration_id, text
            )
        except FathomError as exc:
            return [{"error": exc.detail}]
        return [
            o.model_dump(exclude_none=True, exclude={"parameters", "fields"}) for o in found[:25]
        ]

    @agent.tool
    async def describe_operation(
        ctx: RunContext[AgentDeps], integration_id: str, operation: str
    ) -> dict[str, Any]:
        """One operation: its parameters, where its list is, and every item field with its type."""
        try:
            view = await ctx.deps.container.integrations.describe_operation(
                ctx.deps.principal, integration_id, operation
            )
        except FathomError as exc:
            return {"error": exc.detail}
        return view.model_dump(exclude_none=True)

    @agent.tool
    async def validate_query(
        ctx: RunContext[AgentDeps], definition: dict[str, Any]
    ) -> dict[str, Any]:
        """Statically check a query definition (integration_id, name, version, operation,
        params, items, fields, and for AWS regions and for_each). Problems carry JSON pointers
        into the definition; fix them and validate again."""
        try:
            write = QueryWrite.model_validate(definition)
        except ValueError as exc:
            return {"valid": False, "errors": [{"pointer": "", "detail": str(exc)}]}
        check = await ctx.deps.container.integrations.validate_query(ctx.deps.principal, write)
        return check.model_dump(exclude_none=True)

    @agent.tool
    async def dry_run_query(
        ctx: RunContext[AgentDeps], definition: dict[str, Any], connection_id: str
    ) -> dict[str, Any]:
        """Sample a query definition through a connection. Nothing is stored. Warnings name
        fields that came back empty, which usually means a wrong path."""
        try:
            request = DryRunRequest.model_validate(
                {**definition, "connection_id": connection_id, "max_items": SAMPLE_ITEMS}
            )
        except ValueError as exc:
            return {"error": str(exc)}
        try:
            run = await ctx.deps.container.integrations.dry_run(ctx.deps.principal, request)
        except FathomError as exc:
            return {"error": exc.detail}
        return run.model_dump(exclude_none=True)

    @agent.tool
    async def preview_rule(
        ctx: RunContext[AgentDeps],
        run: dict[str, Any],
        items: list[dict[str, Any]] | None = None,
        definition: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Evaluate a rule run block (source, select, assert, aggregate) over the latest
        snapshots, or over `items` from a dry run of the unsaved `definition`."""
        try:
            request = RulePreviewRequest.model_validate(
                {
                    "run": run,
                    **({"items": items} if items is not None else {}),
                    **({"query": definition} if definition else {}),
                    "limit": SAMPLE_ITEMS,
                }
            )
            preview = await ctx.deps.container.integrations.preview_rule(
                ctx.deps.principal, request
            )
        except (ValueError, FathomError) as exc:
            return {"error": getattr(exc, "detail", str(exc))}
        return preview.model_dump(exclude_none=True)

    @agent.tool
    async def propose_query_source(
        ctx: RunContext[AgentDeps],
        definition: dict[str, Any],
        rule: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Hand a validated query definition (and optionally the rule run block that reads
        it) to the person as a draft in the query editor. This saves nothing: a person
        reviews the draft, its sample, and its preview, and saves it."""
        try:
            write = QueryWrite.model_validate(definition)
        except ValueError as exc:
            return {"proposed": False, "errors": [{"pointer": "", "detail": str(exc)}]}
        check = await ctx.deps.container.integrations.validate_query(ctx.deps.principal, write)
        if not check.valid:
            return {"proposed": False, "errors": [e.model_dump() for e in check.errors]}
        ctx.deps.created_drafts.append(
            {
                "object_type": "query_source",
                "id": check.source,
                "label": f"Draft query source: {check.source}",
                "definition": write.model_dump(exclude_none=True),
                **({"rule": rule} if rule else {}),
            }
        )
        return {"proposed": True, "source": check.source}
