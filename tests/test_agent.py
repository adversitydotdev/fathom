"""Tests for the Pydantic AI agent package and RFC 0003 §4 hard-coded write gates."""

from __future__ import annotations

import asyncio
import json

import pytest
from fastapi.testclient import TestClient
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel

from fathom import container
from fathom.access import ActorKind, Principal, Role
from fathom.agent import AgentConfig, agent_principal, draft_gap_remediation
from fathom.api.app import create_app
from fathom.errors import Forbidden
from fathom.kernel.models import parse
from fathom.operations import types as t
from fathom.persistence.memory import MemoryStore
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


def test_agent_config_env_detection():
    empty = AgentConfig.from_env({})
    assert not empty.enabled
    assert empty.hint

    anth = AgentConfig.from_env({"ANTHROPIC_API_KEY": "sk-ant-test"})
    assert anth.enabled
    assert anth.provider == "anthropic"
    assert anth.model_name == "anthropic:claude-sonnet-4-5"

    oai = AgentConfig.from_env({"OPENAI_API_KEY": "sk-test"})
    assert oai.enabled
    assert oai.provider == "openai"
    assert oai.model_name == "openai:gpt-4o"

    local = AgentConfig.from_env(
        {"FATHOM_AI_BASE_URL": "http://localhost:11434/v1", "FATHOM_AI_MODEL": "openai:llama3.2"}
    )
    assert local.enabled
    assert local.provider == "openai"


def test_agent_http_status_and_sse_stream():
    async def scripted_stream(messages: list[ModelMessage], info: AgentInfo):
        del info
        if len(messages) == 1:
            yield {
                0: DeltaToolCall(
                    name="draft_implementation",
                    json_args=json.dumps(
                        {
                            "system_ref": "system--com.acme.prod",
                            "control_ref": C1,
                            "narrative": "Streamed draft narrative for C1.",
                        }
                    ),
                )
            }
        else:
            yield "Created a planned "
            yield "draft for review."

    class _AdminAuth:
        async def authenticate(self, credentials):
            del credentials
            return Principal(
                "party--com.acme.admin",
                "organization",
                ActorKind.PERSON,
                frozenset({Role.ADMINISTRATOR}),
            )

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
    ]
    c = container.build(
        authenticator=_AdminAuth(),
        store=MemoryStore(library=lib, organization=org),
        agent_config=AgentConfig(model_override=FunctionModel(stream_function=scripted_stream)),
    )
    client = TestClient(create_app(c))
    headers = {"Authorization": "Bearer any"}

    status_res = client.get("/v1/agent/status", headers=headers)
    assert status_res.status_code == 200
    assert status_res.json()["enabled"] is True

    stream_res = client.post(
        "/v1/agent/stream",
        headers=headers,
        json={
            "message": "Draft implementation for C1",
            "context": {"system_id": "system--com.acme.prod"},
        },
    )
    assert stream_res.status_code == 200
    events = [
        json.loads(line.removeprefix("data: "))
        for line in stream_res.text.splitlines()
        if line.startswith("data: ")
    ]
    types = [e["type"] for e in events]
    assert "tool_call" in types
    assert "draft" in types
    assert "done" in types
    done = next(e for e in events if e["type"] == "done")
    assert "planned draft" in done["text"]
    assert len(done["drafts"]) == 1
    assert done["drafts"][0]["object_type"] == "implementation"
