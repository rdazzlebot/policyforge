"""Calls a model hosted on Amazon Bedrock via its Converse API, which uses
the same request/response shape regardless of which underlying model
provider (Anthropic, Meta, Amazon, etc.) is serving the model — nothing
provider-specific to special-case here.

Auth deliberately isn't an `api_key_env` like AnthropicProvider: Bedrock
uses AWS's standard credential chain (environment variables, `~/.aws/
credentials`, an IAM role, ...) via `boto3`, so there's no single key to
name in config.yaml. Configure credentials the normal AWS way; this
provider only needs a region and a model ID.
"""

from __future__ import annotations

from .base import LLMProvider, LLMResponse


class BedrockProvider(LLMProvider):
    """Calls a model on Amazon Bedrock via the Converse API.

    Requires the `boto3` package — install with
    `pip install "policyforge[bedrock]"` — and AWS credentials configured
    through boto3's normal credential chain, never a literal key in
    config.yaml.
    """

    def __init__(self, *, model: str, region: str = "us-east-1", client=None):
        self.model = model
        self.region = region
        if client is not None:
            # Dependency injection point for tests, so exercising the
            # request/response handling below doesn't require boto3 (or
            # live AWS credentials) to be installed.
            self._client = client
            return
        try:
            import boto3
        except ImportError as exc:
            raise RuntimeError(
                "The 'boto3' package is required for the bedrock provider. "
                'Install it with: pip install "policyforge[bedrock]"'
            ) from exc
        self._client = boto3.client("bedrock-runtime", region_name=region)

    def generate(
        self,
        *,
        system: str,
        prompt: str,
        max_tokens: int = 4096,
        temperature: float = 0.2,
    ) -> LLMResponse:
        response = self._client.converse(
            modelId=self.model,
            system=[{"text": system}],
            messages=[{"role": "user", "content": [{"text": prompt}]}],
            inferenceConfig={"maxTokens": max_tokens, "temperature": temperature},
        )
        text = "".join(
            block["text"] for block in response["output"]["message"]["content"] if "text" in block
        )
        usage = response.get("usage", {})
        return LLMResponse(
            text=text,
            model=self.model,
            input_tokens=usage.get("inputTokens"),
            output_tokens=usage.get("outputTokens"),
        )

    def check(self) -> bool:
        """Cheap round-trip to confirm credentials + model actually work."""
        result = self.generate(
            system="Reply with exactly one word.",
            prompt="Reply with the word: ok",
            max_tokens=8,
            temperature=0,
        )
        return "ok" in result.text.lower()
