"""Provider-agnostic LLM interface.

v1 ships a single concrete provider (Anthropic's API directly). Everything
that calls an LLM in this codebase should depend on this interface, not on
`anthropic` directly — that's what makes it possible to add a
VertexProvider or BedrockProvider later without touching mapping/,
synthesis/, or generate/.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class LLMResponse:
    text: str
    model: str
    input_tokens: int | None = None
    output_tokens: int | None = None


class LLMProvider(ABC):
    """Minimal surface every provider must implement."""

    @abstractmethod
    def generate(
        self,
        *,
        system: str,
        prompt: str,
        max_tokens: int = 4096,
        temperature: float = 0.2,
    ) -> LLMResponse:
        """Send a single-turn request and return the completion."""
        raise NotImplementedError

    @abstractmethod
    def check(self) -> bool:
        """Cheap connectivity/auth check. Used by `policyforge llm-check`."""
        raise NotImplementedError


def get_provider(config: dict) -> LLMProvider:
    """Factory: build the configured provider from config['llm'].

    Adding a new provider later means: write a new class implementing
    LLMProvider, register it in this dict, and nothing else in the codebase
    changes.
    """
    provider_name = config["llm"]["provider"]

    if provider_name == "anthropic":
        from .anthropic_provider import AnthropicProvider

        return AnthropicProvider(
            model=config["llm"]["model"],
            api_key_env=config["llm"]["api_key_env"],
        )

    if provider_name == "bedrock":
        from .bedrock_provider import BedrockProvider

        return BedrockProvider(
            model=config["llm"]["model"],
            region=config["llm"].get("region", "us-east-1"),
        )

    raise ValueError(
        f"Unknown llm.provider '{provider_name}'. "
        "Supported: anthropic, bedrock. (A Vertex AI Model Garden provider "
        "is a planned follow-up — see README roadmap.)"
    )
