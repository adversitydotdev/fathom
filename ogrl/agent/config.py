"""Runtime model configuration for the OGRL AI assistant (RFC 0003 §4 & §12).

Supports both Anthropic (Claude) and OpenAI-compatible providers (OpenAI,
OpenRouter, Ollama, LiteLLM, vLLM) via environment variables:

- `OGRL_AI_MODEL`: explicit model spec (e.g. `anthropic:claude-sonnet-4-5`,
  `openai:gpt-4o`, or `openai:llama3.2` when paired with `OGRL_AI_BASE_URL`).
- `ANTHROPIC_API_KEY`: enables Anthropic (defaults to `anthropic:claude-sonnet-4-5`).
- `OPENAI_API_KEY`: enables OpenAI (defaults to `openai:gpt-4o`).
- `OGRL_AI_BASE_URL` / `OGRL_AI_API_KEY`: custom OpenAI-compatible endpoint/key.
- `OGRL_AI_ACTOR_ID`: party ID stamped onto agent drafts (`party--ogrl-agent`).
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass

from pydantic_ai.models import Model

from ogrl.agent.deps import DEFAULT_AGENT_ID

DEFAULT_ANTHROPIC_MODEL = "anthropic:claude-sonnet-4-5"
DEFAULT_OPENAI_MODEL = "openai:gpt-4o"


@dataclass(frozen=True)
class AgentConfig:
    model_name: str | None = None
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None
    base_url: str | None = None
    actor_id: str = DEFAULT_AGENT_ID
    model_override: Model | None = None

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> AgentConfig:
        src = os.environ if env is None else env
        explicit = (src.get("OGRL_AI_MODEL") or "").strip() or None
        generic_key = (src.get("OGRL_AI_API_KEY") or "").strip() or None
        anthropic_key = (src.get("ANTHROPIC_API_KEY") or "").strip() or None
        openai_key = (src.get("OPENAI_API_KEY") or "").strip() or None
        base_url = (src.get("OGRL_AI_BASE_URL") or "").strip() or None
        actor_id = (src.get("OGRL_AI_ACTOR_ID") or "").strip() or DEFAULT_AGENT_ID

        model_name = explicit
        if model_name is None:
            if anthropic_key:
                model_name = DEFAULT_ANTHROPIC_MODEL
            elif openai_key or base_url:
                model_name = DEFAULT_OPENAI_MODEL
            elif generic_key:
                model_name = (
                    DEFAULT_ANTHROPIC_MODEL
                    if generic_key.startswith("sk-ant-")
                    else DEFAULT_OPENAI_MODEL
                )

        if generic_key:
            if (model_name or "").startswith("anthropic:"):
                anthropic_key = anthropic_key or generic_key
            else:
                openai_key = openai_key or generic_key

        return cls(
            model_name=model_name,
            anthropic_api_key=anthropic_key,
            openai_api_key=openai_key,
            base_url=base_url,
            actor_id=actor_id,
        )

    @property
    def enabled(self) -> bool:
        if self.model_override is not None:
            return True
        if not self.model_name:
            return False
        if self.model_name.startswith("anthropic:"):
            return bool(self.anthropic_api_key)
        if self.model_name.startswith("openai:"):
            return bool(self.openai_api_key or self.base_url)
        return True

    @property
    def provider(self) -> str | None:
        if self.model_override is not None:
            return "test"
        if not self.model_name:
            return None
        if ":" in self.model_name:
            return self.model_name.split(":", 1)[0]
        return "custom"

    @property
    def display_model(self) -> str | None:
        if self.model_override is not None:
            return "test-model"
        return self.model_name

    @property
    def hint(self) -> str | None:
        if self.enabled:
            return None
        return (
            "Set ANTHROPIC_API_KEY (for Claude) or OPENAI_API_KEY / OGRL_AI_BASE_URL "
            "(for OpenAI-compatible models) and restart the api service."
        )

    def resolve_model(self) -> Model | str:
        if self.model_override is not None:
            return self.model_override
        if not self.model_name:
            raise RuntimeError(self.hint or "AI model is not configured.")

        if self.model_name.startswith("anthropic:"):
            from pydantic_ai.models.anthropic import AnthropicModel
            from pydantic_ai.providers.anthropic import AnthropicProvider

            bare = self.model_name.split(":", 1)[1]
            return AnthropicModel(
                bare,
                provider=AnthropicProvider(api_key=self.anthropic_api_key),
            )

        if self.model_name.startswith("openai:"):
            from pydantic_ai.models.openai import OpenAIChatModel
            from pydantic_ai.providers.openai import OpenAIProvider

            bare = self.model_name.split(":", 1)[1]
            return OpenAIChatModel(
                bare,
                provider=OpenAIProvider(
                    base_url=self.base_url,
                    api_key=self.openai_api_key or ("local" if self.base_url else None),
                ),
            )

        return self.model_name
