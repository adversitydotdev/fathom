"""AI assistant HTTP route declarations (RFC 0003 §4)."""

from http import HTTPMethod

from pydantic import BaseModel

from fathom.access import Permission as P
from fathom.api.paths.endpoint import Endpoint


class AgentStatus(BaseModel):
    enabled: bool
    model: str | None = None
    provider: str | None = None
    actor_id: str
    hint: str | None = None


class AgentHistoryTurn(BaseModel):
    role: str
    content: str


class AgentContext(BaseModel):
    program_id: str | None = None
    system_id: str | None = None
    control_id: str | None = None
    route: str | None = None


class AgentStreamRequest(BaseModel):
    message: str
    history: list[AgentHistoryTurn] = []
    context: AgentContext | None = None


GET_AGENT_STATUS = Endpoint(
    id="getAgentStatus",
    summary="Report whether an AI model is configured and which model/provider is active.",
    method=HTTPMethod.GET,
    path="/agent/status",
    tag="Agent",
    permission=P.PROGRAMS_READ,
    response=AgentStatus,
)

STREAM_AGENT = Endpoint(
    id="streamAgent",
    summary="Run one AI assistant turn as an SSE stream under RFC 0003 §4 write gates.",
    method=HTTPMethod.POST,
    path="/agent/stream",
    tag="Agent",
    permission=P.PROGRAMS_READ,
)

ALL = (GET_AGENT_STATUS, STREAM_AGENT)
