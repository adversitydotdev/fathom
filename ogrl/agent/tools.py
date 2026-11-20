"""Typed Pydantic AI tools wrapping OGRL application services (RFC 0003 §4)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic_ai import Agent, RunContext

from ogrl.agent.deps import AgentDeps
from ogrl.operations import types as t
from ogrl.operations.pagination import PageRequest


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
        """Create a `draft` policy and store its Markdown body in object storage for human review."""
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
