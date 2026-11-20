"""Tests for the Pydantic AI agent package and RFC 0003 §4 hard-coded write gates."""

from __future__ import annotations

import asyncio

import pytest
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from ogrl import container
from ogrl.access import ActorKind, Principal, Role
from ogrl.agent import agent_principal, draft_gap_remediation
from ogrl.errors import Forbidden
from ogrl.kernel.models import parse
from ogrl.operations import types as t
from ogrl.persistence.memory import MemoryStore
from tests.conftest import C1, LIB_BASELINE, library_objects


class _NoopAuth:
    async def authenticate(self, credentials):
        del credentials
        return None


def _seeded_container() -> container.Container:
    lib = [parse(o) for o in library_objects()]
    stamp = "2026-11-20T00:00:00Z"
    org = [
        parse(
            {
                "type": "system",
                "id": "system--com.acme.prod",
                "created": stamp,
                "modified": stamp,
                "name": "Prod",
            }
        ),
        parse(
            {
                "type": "program",
                "id": "program--com.acme.fed",
                "created": stamp,
                "modified": stamp,
                "name": "Fed",
                "system_ref": "system--com.acme.prod",
                "baseline_ref": LIB_BASELINE,
            }
        ),
    ]
    store = MemoryStore(library=lib, organization=org)
    return container.build(authenticator=_NoopAuth(), store=store)


def test_agent_reads_gaps_and_drafts_planned_implementation():
    c = _seeded_container()

    def scripted_model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        del info
        # Step 1: inspect system gaps
        if len(messages) == 1:
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        tool_name="get_system_gaps",
                        args={"system_id": "system--com.acme.prod"},
                    )
                ]
            )
        # Step 2: draft a planned implementation for C1
        if len(messages) == 3:
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        tool_name="draft_implementation",
                        args={
                            "system_ref": "system--com.acme.prod",
                            "control_ref": C1,
                            "narrative": "Draft: enforce centralized IdP lifecycle workflows.",
                        },
                    )
                ]
            )
        # Step 3: finish with summary text
        return ModelResponse(
            parts=[TextPart(content="Drafted planned implementation for human review.")]
        )

    result = asyncio.run(
        draft_gap_remediation(
            c,
            system_id="system--com.acme.prod",
            model=FunctionModel(scripted_model),
            actor_id="party--com.acme.assistant",
        )
    )
    assert "human review" in result.output

    admin = Principal(
        "party--com.acme.admin", "organization", ActorKind.PERSON, frozenset({Role.ADMINISTRATOR})
    )
    impls = asyncio.run(c.objects.list(admin, t.IMPLEMENTATION, t.ImplementationQuery())).data
    assert len(impls) == 1
    assert impls[0].status == "planned"
    assert impls[0].created_by_ref == "party--com.acme.assistant"


def test_agent_write_gates_block_privileged_actions():
    c = _seeded_container()
    bot = agent_principal("party--com.acme.assistant")

    async def verify_blocks() -> None:
        # Cannot attest an implementation as `implemented`
        with pytest.raises(Forbidden):
            await c.objects.create(
                bot,
                t.IMPLEMENTATION,
                {
                    "system_ref": "system--com.acme.prod",
                    "control_ref": C1,
                    "status": "implemented",
                    "responsibility": "provider",
                    "narrative": "Should be blocked",
                },
            )
        # Cannot author a `test.run` block
        with pytest.raises(Forbidden):
            await c.objects.create(
                bot,
                t.TEST,
                {
                    "name": "sneaky",
                    "control_ref": C1,
                    "method": "automated",
                    "run": {"runner": "shell", "command": "echo hi"},
                },
            )
        # Cannot create a reviewed mapping
        with pytest.raises(Forbidden):
            await c.objects.create(
                bot,
                t.MAPPING,
                {
                    "source_ref": C1,
                    "target_ref": "requirement--nist-sp-800-53-r5-ac-2",
                    "relationship": "equivalent-to",
                    "review_status": "reviewed",
                },
            )
        # Can draft a planned implementation, then cannot revoke it
        draft = await c.objects.create(
            bot,
            t.IMPLEMENTATION,
            {
                "system_ref": "system--com.acme.prod",
                "control_ref": C1,
                "status": "planned",
                "responsibility": "provider",
                "narrative": "Allowed draft",
            },
        )
        with pytest.raises(Forbidden):
            await c.objects.revoke(bot, t.IMPLEMENTATION, draft.id, draft.modified)

    asyncio.run(verify_blocks())
