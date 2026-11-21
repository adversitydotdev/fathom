"""FastAPI handlers for the AI assistant (RFC 0003 §4)."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

from fastapi.responses import StreamingResponse

from ogrl.access import Principal
from ogrl.agent import stream_agent_turn
from ogrl.api import paths
from ogrl.api.paths.agent import AgentStatus, AgentStreamRequest
from ogrl.api.registrar import CurrentPrincipal, Registrar
from ogrl.container import Container


def register(registrar: Registrar, c: Container) -> None:
    async def get_status(principal: CurrentPrincipal) -> AgentStatus:
        del principal
        cfg = c.agent_config
        return AgentStatus(
            enabled=cfg.enabled,
            model=cfg.display_model,
            provider=cfg.provider,
            actor_id=cfg.actor_id,
            hint=cfg.hint,
        )

    async def stream(body: AgentStreamRequest, principal: CurrentPrincipal) -> StreamingResponse:
        # Note: authenticated user permission (`PROGRAMS_READ`) was already checked by
        # Registrar; all agent tool writes execute under `ActorKind.AGENT` (RFC 0003 §4),
        # never inheriting the human caller's admin/contributor roles.
        _unused: Principal = principal
        del _unused

        history = [{"role": h.role, "content": h.content} for h in body.history]
        ctx = body.context.model_dump(exclude_none=True) if body.context else None

        async def event_gen() -> AsyncIterator[str]:
            async for event in stream_agent_turn(
                c,
                config=c.agent_config,
                message=body.message,
                history=history,
                context=ctx,
            ):
                yield f"data: {json.dumps(event)}\n\n"

        return StreamingResponse(
            event_gen(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    registrar.handle(paths.agent.GET_AGENT_STATUS, get_status)
    registrar.handle(paths.agent.STREAM_AGENT, stream)
