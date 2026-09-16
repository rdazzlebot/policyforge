"""How hard a model should think, chosen per call site.

The token budgets in `zardoz/budgets.py` exist because of a shape this
project measured rather than guessed: a reasoning model spends its ceiling
thinking before a one-word answer, so a routing call asking for a single
word needed 800 tokens of headroom and still came back empty one time in
eight. `_anthropic_compat` carries a retry for the same reason, at eight
times the budget.

Both are workarounds for the wrong lever. On current Claude models thinking
is adaptive and `output_config.effort` is the dial: how much the model
spends deliberating is the thing to set, not how much room its deliberation
is allowed to consume. Effort is per request, so it belongs at the call
site — the same request that knows whether it is routing a question or
drafting a Standard.

The tiers below are the ones the budgets already expressed. A call that
picks one word from a closed list, rewrites a question, or lists search
terms is `LOW`. A call that writes a document somebody will be audited
against is `HIGH`.

Nothing here lowers a budget. The budgets were measured, and changing them
is a measured change: `MEASUREMENTS.md` epoch 2 records what happened when
they were set too tight, and the same evidence is owed before setting them
back down. Effort goes in first, and the budgets come down when a sweep says
they can.
"""

from __future__ import annotations

LOW = "low"
MEDIUM = "medium"
HIGH = "high"

#: One word from a closed list. Deliberation here is the failure mode, not
#: the goal — the router that thinks its way past "documents" has made the
#: shell worse.
ROUTING = LOW
#: A question rewritten into the question it obviously means.
RESOLUTION = LOW
#: The document's own vocabulary, guessed. Wrong guesses cost a retrieval,
#: not a document.
EXPANSION = LOW
#: Reading passages and writing a grounded answer with citations. Mid: the
#: claims have to be checked against the passages, and that is reasoning,
#: but an answer is not a document.
ANSWERING = MEDIUM
#: Judging whether a passage carries a claim. The whole point of the call is
#: the judgement.
ENTAILMENT = MEDIUM
#: Grouping page titles nobody's naming convention reached. A judgement, but
#: over titles rather than requirements, and a wrong group is a proposal a
#: person declines rather than a document they publish.
CLUSTERING = MEDIUM
#: Merging framework requirements into statements a policy is built from.
SYNTHESIS = HIGH
#: Drafting a Standard, Policy or Procedure, and planning or applying an
#: edit to a published one. These are the documents an assessor reads.
DRAFTING = HIGH
EDITING = HIGH
#: One control narrative for a System Security Plan.
NARRATIVE = HIGH


def accepts_effort(provider) -> bool:
    """Whether this provider will actually act on an effort level.

    Asked rather than assumed, for the reason `supports_schema` is asked:
    a provider that cannot honour the parameter would have to accept it and
    ignore it, and the call site would then believe it had set something.
    Read through `getattr` because providers here are duck-typed — the fakes
    in the test suite implement `generate` and nothing else.
    """
    ask = getattr(provider, "supports_effort", None)
    return bool(ask and ask())


def accepts_caching(provider) -> bool:
    """Whether this provider will actually mark a cacheable prefix."""
    ask = getattr(provider, "supports_caching", None)
    return bool(ask and ask())


def call(
    provider,
    *,
    effort: str | None = None,
    cache: bool = False,
    cache_prefix: str | None = None,
    **kwargs,
):
    """`provider.generate(**kwargs)`, with the parts a provider can honour.

    The single place that knows how to ask. A provider that advertises
    neither is called exactly as before — not handed parameters it would
    drop, which would let the call site believe it had asked for less
    deliberation, or for a tenth of the price on the half of the request
    that never changes.

    `cache` marks the stable region so the API can serve it from the prompt
    cache; `cache_prefix` says how much of the user prompt belongs to that
    region, for a call site whose leading text repeats every time.
    """
    extra = {}
    if effort is not None and accepts_effort(provider):
        extra["effort"] = effort
    if cache and accepts_caching(provider):
        extra["cache"] = True
        if cache_prefix is not None:
            extra["cache_prefix"] = cache_prefix
    elif cache_prefix is not None:
        # The prefix is part of the prompt, not a hint about it. A provider
        # that cannot mark it still has to be *sent* it, or the call site
        # would silently drop the organization block it split off — which
        # is a different request, not a slower one.
        kwargs["prompt"] = cache_prefix + kwargs["prompt"]
    return provider.generate(**extra, **kwargs)


def call_json(provider, *, effort: str | None = None, **kwargs):
    """`provider.generate_json(**kwargs)`, at `effort` where it means something.

    The schema half of `call`. Kept separate rather than folded in, because
    asking for a schema is a different question from asking for less
    deliberation: `generate_json` refuses outright on a provider that cannot
    constrain a reply, and that refusal is the point — a caller parsing JSON
    that was never guaranteed to be JSON is the failure it exists to remove.
    """
    if effort is not None and accepts_effort(provider):
        return provider.generate_json(effort=effort, **kwargs)
    return provider.generate_json(**kwargs)


def accepts_schema(provider) -> bool:
    """Whether this provider will actually hold a reply to a schema."""
    ask = getattr(provider, "supports_schema", None)
    return bool(ask and ask())


def call_shaped(provider, *, schema: dict, effort: str | None = None, **kwargs):
    """Ask for a shape, and settle for asking nicely where that is all there is.

    `call_json` refuses on a provider that cannot constrain a reply. That is
    right for the entailer, whose whole output is a label from a closed set —
    an unconstrained verdict is not worth having, so not getting one is the
    correct outcome.

    It is wrong for the two callers here. The edit planner and the topic
    clusterer both describe their shape in the system prompt and both parse
    the reply leniently, and they have run that way against local models
    since before any provider here could enforce a schema. Refusing would
    take a working feature away from an Ollama user to gain a guarantee they
    were never relying on. So the schema goes where it can be honoured, the
    prompt keeps asking everywhere, and the lenient parser stays — it is
    still the only thing standing behind a model that answers in prose.
    """
    if accepts_schema(provider):
        return call_json(provider, schema=schema, effort=effort, **kwargs)
    return call(provider, effort=effort, **kwargs)
