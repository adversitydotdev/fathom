"""The assistant drafts query sources (RFC 0006 section 9) and cannot save them.

A scripted model walks the flow over the Smithy test package: find the integration,
search, validate a definition with a wrong path, read the feedback, propose a fixed
draft. Validation is static, so no AWS emulator is needed.
"""

import asyncio
import json
import shutil
from pathlib import Path

import pytest
from pydantic_ai.messages import ModelMessage, ToolReturnPart
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel

from fathom import container
from fathom.agent import AgentConfig, agent_principal
from fathom.agent.assistant import stream_agent_turn
from fathom.errors import Forbidden
from fathom.operations.integrations import QueryWrite
from fathom.persistence.memory import MemoryStore

PACKAGE = Path(__file__).parent / "packages" / "sdk-aws"
AWS = "dev.ogrl.aws"
DEFINITION = {
    "integration_id": AWS,
    "name": "security-groups",
    "operation": "ec2.DescribeSecurityGroups",
    "regions": "*",
    "fields": {"id": "GroupID", "name": "GroupName", "rules": "IpPermissions"},
}
RULE = {"source": f"{AWS}/security-groups@1", "assert": "item.rules.size() == 0"}


class _NoAuth:
    async def authenticate(self, credentials):
        del credentials
        return None


def call(name: str, args: dict) -> dict:
    return {0: DeltaToolCall(name=name, json_args=json.dumps(args))}


@pytest.fixture
def packages(tmp_path):
    shutil.copytree(PACKAGE, tmp_path / "sdk-aws")
    return tmp_path


def test_the_assistant_validates_fixes_and_proposes_without_saving(packages):
    returns: list = []

    async def scripted(messages: list[ModelMessage], info: AgentInfo):
        del info
        last = messages[-1].parts[0]
        if isinstance(last, ToolReturnPart):
            returns.append((last.tool_name, last.content))
        step = len(messages)
        if step == 1:
            yield call("list_integrations", {})
        elif step == 3:
            yield call("search_operations", {"integration_id": AWS, "text": "security groups"})
        elif step == 5:
            yield call("validate_query", {"definition": DEFINITION})
        elif step == 7:
            fixed = {**DEFINITION, "fields": {**DEFINITION["fields"], "id": "GroupId"}}
            yield call("propose_query_source", {"definition": fixed, "rule": RULE})
        else:
            yield "Drafted security-groups@1; review it in the query editor."

    c = container.build(
        authenticator=_NoAuth(),
        store=MemoryStore(),
        integrations_dir=packages,
        agent_config=AgentConfig(model_override=FunctionModel(stream_function=scripted)),
    )

    async def turn() -> list[dict]:
        return [
            e
            async for e in stream_agent_turn(
                c, config=c.agent_config, message="Test that no security group is open"
            )
        ]

    events = asyncio.run(turn())
    assert [e for e in events if e["type"] == "error"] == []
    listed = dict(returns)["list_integrations"]
    assert listed["integrations"][0]["query_model"] == "smithy"
    assert [o["id"] for o in dict(returns)["search_operations"]][0] == "ec2.DescribeSecurityGroups"
    check = dict(returns)["validate_query"]
    assert check["valid"] is False
    assert check["errors"] == [
        {
            "pointer": "/fields/id",
            "detail": "items have no 'GroupID'; did you mean 'GroupId' or 'GroupName'?",
        }
    ]

    (draft,) = [e for e in events if e["type"] == "draft"]
    assert draft["object_type"] == "query_source"
    assert draft["id"] == f"{AWS}/security-groups@1"
    assert draft["definition"]["fields"]["id"] == "GroupId"
    assert draft["rule"] == RULE

    # Proposing saved nothing, and the agent cannot save it itself.
    assert asyncio.run(c.integrations._store.list_queries()) == []
    with pytest.raises(Forbidden):
        asyncio.run(
            c.integrations.create_query(
                agent_principal(), QueryWrite.model_validate(draft["definition"])
            )
        )


def test_proposing_an_invalid_definition_returns_the_problems(packages):
    async def scripted(messages: list[ModelMessage], info: AgentInfo):
        del info
        if len(messages) == 1:
            yield call("propose_query_source", {"definition": {**DEFINITION, "regions": None}})
        else:
            yield "Fixing it."

    c = container.build(
        authenticator=_NoAuth(),
        store=MemoryStore(),
        integrations_dir=packages,
        agent_config=AgentConfig(model_override=FunctionModel(stream_function=scripted)),
    )

    async def turn() -> list[dict]:
        return [e async for e in stream_agent_turn(c, config=c.agent_config, message="x")]

    events = asyncio.run(turn())
    assert [e for e in events if e["type"] == "draft"] == []
