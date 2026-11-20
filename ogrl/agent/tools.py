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
            }
            for c in page.data
        ]

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
    async def draft_implementation(
        ctx: RunContext[AgentDeps],
        system_ref: str,
        control_ref: str,
        narrative: str,
        responsibility: str = "provider",
        parameter_values: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Draft an implementation narrative with `status: planned` for human review."""
        body: dict[str, Any] = {
            "system_ref": system_ref,
            "control_ref": control_ref,
            "status": "planned",
            "responsibility": responsibility,
            "narrative": narrative,
        }
        if parameter_values:
            body["parameter_values"] = parameter_values
        created = await ctx.deps.container.objects.create(
            ctx.deps.principal, t.IMPLEMENTATION, body
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
        return created.body()
