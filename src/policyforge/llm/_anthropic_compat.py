"""Shared internals for AnthropicProvider and VertexProvider: both wrap the
`anthropic` SDK's `messages.create` with the identical request shape (only
how the client itself is constructed/authenticated differs), including the
identical `temperature`-deprecation retry (see anthropic_provider.py's
module docstring for why that retry exists). Not part of the public
LLMProvider interface — provider-specific auth/client setup stays in each
provider's own module.
"""

from __future__ import annotations

from .base import LLMResponse


def call_messages_api(
    client,
    *,
    model: str,
    system: str,
    prompt: str,
    max_tokens: int,
    temperature: float,
) -> LLMResponse:
    import anthropic

    kwargs = dict(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": prompt}],
    )
    try:
        response = client.messages.create(temperature=temperature, **kwargs)
    except anthropic.BadRequestError as exc:
        # Some newer models (e.g. claude-sonnet-5) reject `temperature`
        # outright rather than just ignoring it, so retry without it
        # instead of hard-failing every call on those models.
        if "temperature" in str(exc) and "deprecated" in str(exc):
            response = client.messages.create(**kwargs)
        else:
            raise

    text = "".join(block.text for block in response.content if block.type == "text")
    return LLMResponse(
        text=text,
        model=model,
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
    )
