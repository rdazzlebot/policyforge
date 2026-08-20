from __future__ import annotations

import os

from .base import LLMProvider, LLMResponse


class AnthropicProvider(LLMProvider):
    """Calls Claude directly via the Anthropic API.

    Expects an API key in the environment variable named by `api_key_env`
    (configured in config.yaml, default ANTHROPIC_API_KEY) — never read a
    literal key out of a config file.
    """

    def __init__(self, *, model: str, api_key_env: str = "ANTHROPIC_API_KEY"):
        self.model = model
        self.api_key_env = api_key_env
        api_key = os.environ.get(api_key_env)
        if not api_key:
            raise RuntimeError(
                f"Environment variable {api_key_env} is not set. "
                f"Export your Anthropic API key before running policyforge, e.g.:\n"
                f"  export {api_key_env}=sk-ant-..."
            )
        # Imported lazily so `policyforge` doesn't hard-fail at import time
        # for commands that never touch the LLM (e.g. pure ETL/ingest).
        import anthropic

        self._client = anthropic.Anthropic(api_key=api_key)

    def generate(
        self,
        *,
        system: str,
        prompt: str,
        max_tokens: int = 4096,
        temperature: float = 0.2,
    ) -> LLMResponse:
        response = self._client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(
            block.text for block in response.content if block.type == "text"
        )
        return LLMResponse(
            text=text,
            model=self.model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )

    def check(self) -> bool:
        """Cheap round-trip to confirm the key + model actually work."""
        result = self.generate(
            system="Reply with exactly one word.",
            prompt="Reply with the word: ok",
            max_tokens=8,
            temperature=0,
        )
        return "ok" in result.text.lower()
