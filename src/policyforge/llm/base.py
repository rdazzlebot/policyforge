"""Provider-agnostic LLM interface.

Ships six concrete providers: Anthropic's API directly, Amazon Bedrock,
Google Cloud's Vertex AI Model Garden, any OpenAI-compatible
chat-completions endpoint (a local Ollama/LM Studio/vLLM server, or a
hosted open model), LiteLLM, which reaches most of the rest behind one
model string, and a cascade that pairs two of the above. Everything that
calls an LLM in
this codebase should depend on this interface, not on `anthropic` or a
cloud SDK directly — that's what makes it possible to add another provider
later without touching mapping/, synthesis/, or generate/.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


class SchemaReplyError(RuntimeError):
    """A schema-constrained call came back as something other than JSON.

    A `RuntimeError` so every existing handler still catches it, and its own
    type so a caller can tell "the model answered, just not in the shape
    asked" from a timeout or an auth failure. The first carries a reply worth
    reading (`text`); the second has nothing to recover, and a caller that
    retries on it only doubles the wait.
    """

    def __init__(self, message: str, text: str):
        super().__init__(message)
        self.text = text


@dataclass
class LLMResponse:
    text: str
    model: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    #: What the call cost, in USD, when the provider can say. Only
    #: LiteLLMProvider populates it today — it prices the call from
    #: LiteLLM's own tables — and a local model correctly reports 0.0
    #: rather than None. Left None by every other provider, so a caller
    #: must treat "unknown" and "free" as different answers.
    cost_usd: float | None = None
    #: Why the model stopped. `max_tokens` means the reply was cut off, and
    #: the providers already knew: they read it to decide whether to retry
    #: and then threw it away, so a truncated document reached the caller
    #: looking like a finished one. Now it travels, and the ledger records it.
    stop_reason: str | None = None
    #: Input tokens served from the prompt cache. Zero and None are different
    #: answers: zero means the call could have hit the cache and did not —
    #: which is what a silently-too-short cacheable prefix looks like — and
    #: None means the provider does not report caching at all.
    cached_input_tokens: int | None = None
    #: The provider's own id for the request, which is the first thing
    #: Anthropic support asks for. Free on every response and impossible to
    #: reconstruct afterwards.
    request_id: str | None = None
    #: Spans the API says were quoted, when the request sent its passages as
    #: document blocks. `llm/grounded.py` says what makes these different
    #: from the `[2]` markers a model writes: the text is extracted from the
    #: document rather than generated, so it is verbatim by construction.
    #: None means the request did not ask for citations; an empty list means
    #: it did and the model cited nothing.
    citations: list | None = None


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

    # ---- structured output, opt-in ------------------------------------
    #
    # Deliberately not part of `generate`'s signature. A provider that
    # cannot enforce a schema would have to accept the argument and ignore
    # it, and a caller would then parse JSON that was never guaranteed to
    # be JSON — the silent failure this is supposed to remove. Asking first
    # is the honest shape, and it keeps every existing provider working
    # untouched.
    #
    # Worth having because three unrelated models have now failed the
    # `INSUFFICIENT_CONTEXT` sentinel while being substantively correct,
    # and `parse_expansion` discards a reply of the wrong shape, which is
    # what made one model score 11% on expansion. A schema turns "did the
    # model obey the format" from a graded risk into a guarantee.

    def supports_schema(self) -> bool:
        """Whether `generate_json` will actually constrain the reply."""
        return False

    # ---- effort, opt-in ------------------------------------------------
    #
    # Asked rather than passed, for the same reason as the schema above. A
    # provider that cannot act on an effort level would have to accept the
    # argument and drop it, and the call site would believe it had set
    # something. `llm/effort.py` is where a caller asks.

    def supports_effort(self) -> bool:
        """Whether `generate` will act on an `effort` argument."""
        return False

    def supports_caching(self) -> bool:
        """Whether `generate` will act on `cache` / `cache_prefix`.

        Asked for the same reason again. A provider that cannot mark a
        cacheable prefix would drop the hint, and the high-volume call
        sites would believe they were paying a tenth for the part of the
        request that never changes.
        """
        return False

    # ---- batching, opt-in ----------------------------------------------

    def supports_batch(self) -> bool:
        """Whether `generate_batch` will submit a real batch."""
        return False

    def generate_batch(self, requests, **kwargs) -> dict:
        """Answer many requests together, keyed by each one's `custom_id`.

        Only call this when `supports_batch()` is True. The default refuses
        rather than quietly running the requests one at a time: a caller
        that asked for a batch asked for its price, and a silent fallback
        would bill interactive rates for a run somebody chose to wait on.
        """
        raise NotImplementedError(
            f"{type(self).__name__} cannot submit a batch. "
            f"Check supports_batch() before calling generate_batch()."
        )

    # ---- native citations, opt-in --------------------------------------
    #
    # Asked before use, like everything else here. A provider that cannot
    # send document blocks would have to flatten them into the prompt, and
    # the caller would then believe its citations were verified spans when
    # they were `[n]` markers a model wrote — the exact substitution the
    # mechanism exists to remove.

    def supports_grounding(self) -> bool:
        """Whether `generate_grounded` will send real document blocks."""
        return False

    def generate_grounded(
        self,
        *,
        system: str,
        prompt: str,
        documents: list,
        max_tokens: int = 4096,
        temperature: float = 0.2,
        effort: str | None = None,
    ) -> LLMResponse:
        """Like `generate`, with the passages sent as citable documents.

        Only call this when `supports_grounding()` is True. The default
        refuses rather than quietly inlining the documents into the prompt:
        a caller that asked for citations would get uncited prose back and
        no way to tell, which is worse than the error.
        """
        raise NotImplementedError(
            f"{type(self).__name__} cannot send citable documents. "
            f"Check supports_grounding() before calling generate_grounded()."
        )

    def generate_json(
        self,
        *,
        system: str,
        prompt: str,
        schema: dict,
        max_tokens: int = 4096,
        temperature: float = 0.2,
        effort: str | None = None,
    ) -> LLMResponse:
        """Like `generate`, but the reply is constrained to `schema`.

        Only call this when `supports_schema()` is True; the default
        refuses rather than quietly returning unconstrained prose.
        """
        raise NotImplementedError(
            f"{type(self).__name__} cannot constrain output to a schema. "
            f"Check supports_schema() before calling generate_json()."
        )


def get_provider(config: dict) -> LLMProvider:
    """The configured provider, recording every call it makes.

    The ledger wraps here rather than at each call site because there are
    fourteen call sites across nine modules and the fifteenth is the one
    that would be missed. `llm/ledger.py` says what is recorded and what
    deliberately is not; `llm.ledger.enabled: false` turns it off, which is
    a decision visible in a file rather than a gap nobody notices.
    """
    from .ledger import wrap

    return wrap(_build_provider(config), config)


def _build_provider(config: dict) -> LLMProvider:
    """Factory: build the configured provider from config['llm'].

    Adding a new provider later means: write a new class implementing
    LLMProvider, register it in this dict, and nothing else in the codebase
    changes.

    Separate from `get_provider` so that the cascade branch can recurse
    without wrapping each half in its own ledger — which would write three
    records for one call and make a cascade look like it cost triple.
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

    if provider_name == "vertex":
        from .vertex_provider import VertexProvider

        if "project_id" not in config["llm"]:
            raise ValueError(
                "llm.project_id is required for the vertex provider — set it to your "
                "GCP project ID in config.yaml."
            )
        return VertexProvider(
            model=config["llm"]["model"],
            project_id=config["llm"]["project_id"],
            region=config["llm"].get("region", "us-central1"),
        )

    if provider_name in ("openai-compat", "local"):
        from .openai_compat_provider import OpenAICompatProvider

        if "base_url" not in config["llm"]:
            raise ValueError(
                f"llm.base_url is required for the {provider_name} provider — set it to your "
                "endpoint root, e.g. http://localhost:11434/v1 for Ollama."
            )
        return OpenAICompatProvider(
            model=config["llm"]["model"],
            base_url=config["llm"]["base_url"],
            # Optional here, unlike the anthropic provider: a local server
            # normally authenticates nothing, so absence is not an error.
            api_key_env=config["llm"].get("api_key_env"),
            timeout=config["llm"].get("timeout", 600),
        )

    if provider_name == "litellm":
        from .litellm_provider import LiteLLMProvider

        return LiteLLMProvider(
            model=config["llm"]["model"],
            # Optional: LiteLLM resolves each provider's credentials from
            # its own environment conventions, so most model strings need
            # neither of these.
            api_base=config["llm"].get("api_base"),
            api_key_env=config["llm"].get("api_key_env"),
            timeout=config["llm"].get("timeout", 600),
            num_retries=config["llm"].get("num_retries", 3),
            min_interval_seconds=config["llm"].get("min_interval_seconds", 0.0),
        )

    if provider_name == "cascade":
        from .cascade_provider import CascadeProvider

        # Two nested provider blocks, each in the same shape as a top-level
        # `llm:`. Recursing rather than inventing a second syntax means a
        # cascade can pair anything this factory can already build, and a
        # model string that works standalone works here unchanged.
        for key in ("primary", "escalate_to"):
            if key not in config["llm"]:
                raise ValueError(
                    f"llm.{key} is required for the cascade provider — give it a provider "
                    "block of its own, e.g.\n"
                    "  primary:\n"
                    "    provider: litellm\n"
                    "    model: openrouter/deepseek/deepseek-v4-flash"
                )

        return CascadeProvider(
            primary=_build_provider({"llm": config["llm"]["primary"]}),
            escalate_to=_build_provider({"llm": config["llm"]["escalate_to"]}),
        )

    raise ValueError(
        f"Unknown llm.provider '{provider_name}'. Supported: anthropic, bedrock, "
        "vertex, openai-compat (alias: local), litellm, cascade."
    )
