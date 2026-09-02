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

#: Floor for the retry after a thinking block ate the whole budget. Enough
#: for a reasoning preamble plus a short answer, which is the shape of every
#: small call this project makes: a routing word, a rewritten question, a
#: list of terms.
MIN_RETRY_TOKENS = 256


def _text_of(response) -> str:
    """The text blocks only. A thinking block is not an answer."""
    return "".join(block.text for block in response.content if block.type == "text")


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

    kwargs = {
        "model": model,
        "max_tokens": max_tokens,
        "system": system,
        "messages": [{"role": "user", "content": prompt}],
    }

    send_temperature = True

    def _create(**overrides):
        """One request, remembering whether this model tolerates temperature."""
        nonlocal send_temperature
        payload = {**kwargs, **overrides}
        if not send_temperature:
            return client.messages.create(**payload)
        try:
            return client.messages.create(temperature=temperature, **payload)
        except anthropic.BadRequestError as exc:
            # Some newer models (e.g. claude-sonnet-5) reject `temperature`
            # outright rather than just ignoring it, so retry without it
            # instead of hard-failing every call on those models.
            if "temperature" in str(exc) and "deprecated" in str(exc):
                send_temperature = False
                return client.messages.create(**payload)
            raise

    response = _create()
    text = _text_of(response)

    # A reasoning model emits a thinking block before any text, and those
    # tokens come out of `max_tokens`. On a tight budget the whole
    # allowance can be spent thinking, and the reply comes back with
    # `stop_reason="max_tokens"` and no text block at all.
    #
    # Returning "" for that is the dangerous outcome, because it is
    # indistinguishable from the model deliberately saying nothing — and
    # callers read that as a decision. Zardoz's router treats an empty reply
    # as "not an analysis", so a truncated routing call silently sends a
    # coverage question to the documents instead. Measured at roughly one
    # call in eight on a 12-token budget: intermittent, invisible, and
    # wrong. So a truncation before any text is retried with room to speak.
    if not text and getattr(response, "stop_reason", "") == "max_tokens":
        response = _create(max_tokens=max(max_tokens * 8, MIN_RETRY_TOKENS))
        text = _text_of(response)

    return LLMResponse(
        text=text,
        model=model,
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
    )
