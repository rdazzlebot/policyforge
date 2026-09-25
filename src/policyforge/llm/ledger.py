"""What was sent to which model, when, and at what cost.

Nothing persisted this. `LLMResponse` carries a model string and sometimes a
price, `_Metered` in `scripts/eval_zardoz.py` totals a sweep, and both end
with the process. So two questions that a compliance tool of all things
should be able to answer had no answer at all: *which documents did this
model touch*, and *did licensed content ever leave the boundary*.

The second is why this is a control rather than a log. `llm/boundary.py`
refuses a pairing before the call; this records the call that was allowed.
A rule with no record of its operation is a rule nobody can evidence, which
is the exact criticism this project's own generated Standards make of an
organization that has a policy and no logs.

**It records metadata and never content.** Provider, provider class, model,
subject, content class, token counts, cost, and a SHA-256 prefix of the
prompt. Not the prompt, not the reply. A ledger that quoted what it saw
would take a licensed HITRUST export that correctly went to a local model
and copy it into a file under `output/` — recreating, in the audit trail,
precisely the leak the audit trail exists to disprove. The prompt hash is
enough to say "the same prompt" or "a different prompt" without holding
either.

**A subject is a scope, not an argument.** `LLMProvider.generate()` takes a
system prompt, a user prompt and a budget; it has never been told which
document it is working on and giving it that would mean changing every
provider. So the caller names the subject around the work:

    with ledger.about("standard/authenticator-mgmt", site="generate") as scope:
        document = generate_standard(...)
    record_version(..., metadata=scope.provenance())

Every call made inside that block is attributed to the subject, however deep
in the stack it happens. Calls outside one are recorded with no subject
rather than guessed at — an unattributed entry is a true statement about a
run, and an invented one is not.

**Failing to write is failing.** A ledger that swallowed its own write
errors would report a clean history of a run it did not observe, and the
day that matters is the day somebody is relying on it. Configuration can
turn the ledger off, which is a decision somebody made and can be seen in a
file; a silent drop is neither.
"""

from __future__ import annotations

import contextvars
import dataclasses
import hashlib
import json
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from . import escalation
from .base import LLMProvider, LLMResponse
from .boundary import classify_provider

#: Under `output/`, which is gitignored, because this names every document
#: an organization has drafted and how much each cost.
DEFAULT_LEDGER_PATH = Path("output/.model-log/calls.jsonl")


@dataclass(frozen=True)
class CallRecord:
    """One request to one model."""

    timestamp: str
    provider: str
    provider_class: str
    model: str
    #: What the call was about — a document slug, a control id — or None
    #: when it happened outside any `about()` scope.
    subject: str | None
    #: Which command or code path made it: "generate", "ssp", "zardoz.answer".
    site: str | None
    #: The content class of the subject, when the caller knew it. Recorded
    #: here so the boundary question can be answered from this file alone
    #: rather than by re-deriving it from paths that have since moved.
    content_class: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_usd: float | None = None
    #: First 16 hex characters of SHA-256 over system + prompt. Enough to
    #: tell two prompts apart; not enough to reconstruct either.
    prompt_sha: str = ""
    #: Set when the call raised. It reached the vendor and was billed even
    #: though nothing came back, and a ledger that omitted those would
    #: undercount both the spend and the exposure.
    error: str | None = None
    #: How many texts one embedding or rerank batch carried; None for a
    #: model call. Those channels send a batch rather than a prompt, and the
    #: count is what says how much of the corpus a request exposed.
    items: int | None = None
    #: Why the model stopped, when the provider says. `max_tokens` is the
    #: one worth keeping: the document that call produced is short and looks
    #: finished, and nothing downstream can tell afterwards.
    stop_reason: str | None = None
    #: Input tokens served from the prompt cache. Zero and None differ —
    #: zero is a call that could have hit the cache and did not, which is
    #: what a silently-too-short cacheable prefix looks like from here.
    cached_input_tokens: int | None = None
    #: Output tokens the operator paid for and cannot read — a model's own
    #: reasoning, where the provider reports it. None where the provider
    #: does not report it at all, which is every provider but Gemini today,
    #: so a reader can tell "none happened" from "cannot say". Without this
    #: a reasoning call records a fraction of what it cost, silently, by a
    #: ratio that varies per call.
    hidden_output_tokens: int | None = None
    #: Characters of inline reasoning removed before the reply was
    #: recorded. None where the provider does not strip; zero where it
    #: stripped nothing. Pairs with `hidden_output_tokens`: one is what the
    #: vendor billed and withheld, the other is what it sent and we cut.
    stripped_reasoning_chars: int | None = None
    #: The provider's own id for the request. Free on the response, the
    #: first thing a vendor asks for, and unrecoverable afterwards.
    request_id: str | None = None
    #: Every bigger-budget re-send inside this call, with the billed attempt
    #: before it: its request id, cost and output tokens (#361). The row's
    #: tokens and request id are the LAST attempt's; this is where the
    #: earlier, billed ones are kept. One row per billed request is #343's.
    escalations: tuple = ()

    def as_json(self) -> str:
        return json.dumps(dataclasses.asdict(self))


def prompt_digest(system: str, prompt: str) -> str:
    """A short, stable fingerprint of what was sent.

    Includes both halves and a separator, so moving text from the system
    prompt into the user prompt changes the digest — which it should, since
    for several of the models measured here that change moves the score.
    """
    payload = f"{system}\x00{prompt}".encode()
    return hashlib.sha256(payload).hexdigest()[:16]


# ---- the subject scope ----------------------------------------------------


@dataclass
class Scope:
    """A named piece of work, and the calls made inside it."""

    subject: str
    site: str | None = None
    content_class: str | None = None
    records: list[CallRecord] = field(default_factory=list)

    @property
    def models(self) -> list[str]:
        """Every model that actually answered, in first-seen order.

        A list rather than a string because a cascade can answer one
        document with two different models, and "which model wrote this"
        then has two correct answers. Reporting only the configured one
        would name a model that may not have written a word of it.
        """
        seen: list[str] = []
        for record in self.records:
            if record.model and record.model not in seen:
                seen.append(record.model)
        return seen

    @property
    def cost_usd(self) -> float | None:
        """Total spend, or None when no call reported a price.

        None and 0.0 are different answers: a local model is genuinely free,
        and a provider that does not price its calls is unknown. Collapsing
        them would let an unpriced run read as a free one.
        """
        priced = [r.cost_usd for r in self.records if r.cost_usd is not None]
        return sum(priced) if priced else None

    def provenance(self) -> dict:
        """The stamp to record alongside a generated document.

        Small on purpose — this goes into every version-history entry, and
        the ledger holds the detail. What it has to answer is the question
        that gets asked after a model is found to systematically weaken
        cited requirements: which documents did it touch.
        """
        stamp: dict = {
            "models": self.models,
            "calls": len(self.records),
            "prompt_shas": sorted({r.prompt_sha for r in self.records if r.prompt_sha}),
        }
        if self.records:
            stamp["provider"] = self.records[0].provider
            stamp["provider_class"] = self.records[0].provider_class
        cost = self.cost_usd
        if cost is not None:
            stamp["cost_usd"] = round(cost, 6)
        if self.content_class:
            stamp["content_class"] = self.content_class
        return stamp


#: The scope in force, if any. A ContextVar rather than a module global so
#: that a threaded or async caller does not attribute one document's calls
#: to another's — the failure that would make the record worse than nothing.
_scope: contextvars.ContextVar[Scope | None] = contextvars.ContextVar("policyforge_scope")
_scope.set(None)


@contextmanager
def about(subject: str, *, site: str | None = None, content_class: str | None = None):
    """Attribute every model call made inside this block to `subject`.

    Nests: an inner scope takes over and the outer one resumes afterwards,
    so a command that drafts three documents can name each of them without
    the third inheriting the first's subject.
    """
    scope = Scope(subject=subject, site=site, content_class=content_class)
    token = _scope.set(scope)
    try:
        yield scope
    finally:
        _scope.reset(token)


def current_scope() -> Scope | None:
    return _scope.get(None)


# ---- writing --------------------------------------------------------------


def ledger_config(config: dict | None = None) -> dict:
    return ((config or {}).get("llm") or {}).get("ledger") or {}


def ledger_path(config: dict | None = None) -> Path:
    configured = ledger_config(config).get("path")
    return Path(str(configured)) if configured else DEFAULT_LEDGER_PATH


def ledger_enabled(config: dict | None = None) -> bool:
    """On unless config says otherwise.

    Default-on because the record is the point. Someone who does not want
    one can say so, and their config then carries the statement that they
    decided against it.
    """
    setting = ledger_config(config).get("enabled")
    return True if setting is None else bool(setting)


def append(record: CallRecord, path: Path | None = None) -> None:
    """Append one record. Raises if it cannot be written."""
    destination = path or DEFAULT_LEDGER_PATH
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("a", encoding="utf-8") as handle:
        handle.write(record.as_json() + "\n")


def load(path: Path | None = None) -> list[CallRecord]:
    """Every record on file, oldest first. Empty when nothing is recorded."""
    source = path or DEFAULT_LEDGER_PATH
    if not source.exists():
        return []
    records = []
    for line in source.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            # One torn line — a run killed mid-write — should not make the
            # whole history unreadable. Skipped rather than repaired,
            # because inventing a record is worse than missing one.
            continue
        known = {f.name for f in dataclasses.fields(CallRecord)}
        records.append(CallRecord(**{k: v for k, v in data.items() if k in known}))
    return records


# ---- the recording provider ----------------------------------------------


class RecordingProvider(LLMProvider):
    """Wraps a provider and writes a ledger entry per call.

    A wrapper rather than a line at each call site, because there are
    fourteen call sites across nine modules and the fifteenth is the one
    that would be missed. Everything a caller can do to this object it can
    do to the provider inside it; the only difference is that the file grows.
    """

    def __init__(
        self,
        inner: LLMProvider,
        *,
        provider_name: str,
        provider_class: str,
        path: Path | None = None,
    ):
        self._inner = inner
        self._provider_name = provider_name
        self._provider_class = provider_class
        self._path = path or DEFAULT_LEDGER_PATH

    @property
    def inner(self) -> LLMProvider:
        """The provider underneath, for callers that need the real thing."""
        return self._inner

    @property
    def model(self) -> str:
        return getattr(self._inner, "model", "?")

    def __getattr__(self, name: str):
        """Anything not defined here comes from the provider inside.

        Wrapping every provider in `get_provider` made this necessary rather
        than merely tidy. `_Metered.summary()` in `scripts/eval_zardoz.py`
        reaches for `escalations` and `primary_calls` to report how often a
        cascade needed its stronger half, and an opaque wrapper would have
        made a working cascade indistinguishable from a dead one again —
        the exact regression that counter was added to fix.

        **It does not reach anything `LLMProvider` already defines.** Python
        consults `__getattr__` only after normal lookup fails, and every
        `supports_*` flag exists on the base class as `return False`. So a
        flag this class does not override answers False for every provider,
        whatever the one inside would say — which is how native citations,
        effort, prompt caching and batching all went dark on Anthropic and
        Vertex for two days while every test passed. Each flag is therefore
        delegated explicitly below, and `tests/test_llm_ledger.py` discovers
        the flags from the base class rather than from a list here, so a new
        one cannot be added without the wrapper learning to forward it.
        """
        # Only reached for attributes this class does not define, so the
        # recursion guard is on the one attribute that could be missing
        # during unpickling before __init__ has run.
        if name.startswith("__") or name == "_inner":
            raise AttributeError(name)
        return getattr(self._inner, name)

    def _record(
        self,
        *,
        system: str,
        prompt: str,
        response: LLMResponse | None,
        error: str | None = None,
    ) -> None:
        scope = current_scope()
        record = CallRecord(
            timestamp=datetime.now(timezone.utc).isoformat(),
            provider=self._provider_name,
            provider_class=self._provider_class,
            # The model that *answered*, not the one configured. A cascade
            # that escalated wrote this document with its stronger half, and
            # a record naming the cheap one would be false in exactly the
            # situation the record exists for.
            model=(response.model if response is not None else self.model),
            subject=scope.subject if scope else None,
            site=scope.site if scope else None,
            content_class=scope.content_class if scope else None,
            input_tokens=response.input_tokens if response else None,
            output_tokens=response.output_tokens if response else None,
            cost_usd=response.cost_usd if response else None,
            stop_reason=response.stop_reason if response else None,
            cached_input_tokens=response.cached_input_tokens if response else None,
            hidden_output_tokens=response.hidden_output_tokens if response else None,
            stripped_reasoning_chars=(response.stripped_reasoning_chars if response else None),
            request_id=response.request_id if response else None,
            prompt_sha=prompt_digest(system, prompt),
            error=error,
            escalations=escalation.take(),
        )
        append(record, self._path)
        if scope is not None:
            scope.records.append(record)

    def generate(
        self,
        *,
        system: str,
        prompt: str,
        max_tokens: int = 4096,
        temperature: float = 0.2,
        **kwargs,
    ) -> LLMResponse:
        # `**kwargs` carries `effort`, `cache` and `cache_prefix`, which
        # `llm/effort.py` passes only after asking the flags above. With the
        # flags forwarded, a fixed signature here would turn every such call
        # into a TypeError — the flags and the arguments travel together.
        try:
            response = self._inner.generate(
                system=system,
                prompt=prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                **kwargs,
            )
        except Exception as exc:
            # Recorded before re-raising. The request reached the vendor and
            # was billed, and the content in it was exposed whether or not a
            # reply came back — which is the half a spend-only meter misses.
            self._record(system=system, prompt=prompt, response=None, error=type(exc).__name__)
            raise
        self._record(system=system, prompt=prompt, response=response)
        return response

    def generate_batch(self, requests, **kwargs) -> dict:
        """A batch is recorded too, one entry per request.

        Without this, `__getattr__` would have found the inner provider's
        method and several hundred narratives would have reached a vendor
        with nothing in the ledger to say so — which is the one thing the
        wrapper exists to make impossible.
        """
        try:
            answers = self._inner.generate_batch(requests, **kwargs)
        except Exception as exc:
            # Submitted and billed or not, the content left this machine.
            for request in requests:
                self._record(
                    system=request.system,
                    prompt=request.prompt,
                    response=None,
                    error=type(exc).__name__,
                )
            raise
        scope = current_scope()
        for request in requests:
            # Attributed to the request's own id, not to the submission. The
            # per-call scope is what answers "which controls did that model
            # write narratives for", and a batch would otherwise file several
            # hundred narratives under one subject.
            with about(
                request.custom_id,
                site=scope.site if scope else None,
                content_class=scope.content_class if scope else None,
            ):
                self._record(
                    system=request.system,
                    prompt=request.prompt,
                    response=answers.get(request.custom_id),
                )
        return answers

    # ---- capability flags, each delegated by hand -----------------------
    #
    # See `__getattr__`: a flag left out here is answered by the base class,
    # not by the provider inside, and the answer is always False. Asked
    # through `getattr`, as `llm/effort.py` asks, because providers are
    # duck-typed: the fakes in the test suite implement `generate` and
    # little else, and one that never heard of a flag does not support it.

    def _inner_supports(self, flag: str) -> bool:
        ask = getattr(self._inner, flag, None)
        return bool(ask and ask())

    def supports_schema(self) -> bool:
        return self._inner_supports("supports_schema")

    def supports_effort(self) -> bool:
        return self._inner_supports("supports_effort")

    def supports_caching(self) -> bool:
        return self._inner_supports("supports_caching")

    def supports_batch(self) -> bool:
        return self._inner_supports("supports_batch")

    def supports_grounding(self) -> bool:
        return self._inner_supports("supports_grounding")

    def generate_json(self, *, system: str, prompt: str, schema: dict, **kwargs) -> LLMResponse:
        try:
            response = self._inner.generate_json(
                system=system, prompt=prompt, schema=schema, **kwargs
            )
        except Exception as exc:
            self._record(system=system, prompt=prompt, response=None, error=type(exc).__name__)
            raise
        self._record(system=system, prompt=prompt, response=response)
        return response

    def generate_grounded(
        self, *, system: str, prompt: str, documents: list, **kwargs
    ) -> LLMResponse:
        """Recorded like `generate_json`.

        The passages go to the vendor as document blocks rather than inside
        the prompt, so they are exposed exactly as a prompt would be — and
        the digest covers only `system` and `prompt`, because hashing the
        documents would make the record depend on the retrieved text
        without saying anything more about which call this was.
        """
        try:
            response = self._inner.generate_grounded(
                system=system, prompt=prompt, documents=documents, **kwargs
            )
        except Exception as exc:
            self._record(system=system, prompt=prompt, response=None, error=type(exc).__name__)
            raise
        self._record(system=system, prompt=prompt, response=response)
        return response

    def check(self) -> bool:
        """Not recorded.

        `llm-check` sends a fixed two-word probe and is run to find out
        whether a key works. Filling the ledger with those would bury the
        calls that saw real content under the ones that saw none.
        """
        return self._inner.check()


def wrap(provider: LLMProvider, config: dict) -> LLMProvider:
    """Wrap `provider` in a ledger, unless config turned it off."""
    if not ledger_enabled(config):
        return provider
    llm = config.get("llm") or {}
    return RecordingProvider(
        provider,
        provider_name=str(llm.get("provider", "?")),
        provider_class=classify_provider(llm).klass,
        path=ledger_path(config),
    )


# ---- reading it back ------------------------------------------------------


@dataclass
class Totals:
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    #: Summed like the others, but `hidden_reported` says whether any call
    #: in the group could report it. A zero here with nothing reporting
    #: means "unknown", not "none".
    hidden_output_tokens: int = 0
    hidden_reported: bool = False
    cost_usd: float = 0.0
    #: False when no call in the group reported a price, so a zero total can
    #: be read as "free" or "unknown" and not silently as the former.
    priced: bool = False
    errors: int = 0

    def add(self, record: CallRecord) -> None:
        self.calls += 1
        self.input_tokens += record.input_tokens or 0
        self.output_tokens += record.output_tokens or 0
        if record.hidden_output_tokens is not None:
            self.hidden_output_tokens += record.hidden_output_tokens
            self.hidden_reported = True
        if record.cost_usd is not None:
            self.cost_usd += record.cost_usd
            self.priced = True
        if record.error:
            self.errors += 1

    @property
    def cost(self) -> str:
        return f"${self.cost_usd:.4f}" if self.priced else "unpriced"


def summarize(records: list[CallRecord], by: str) -> dict[str, Totals]:
    """Group records by one of their fields and total each group."""
    grouped: dict[str, Totals] = {}
    for record in records:
        key = getattr(record, by, None) or "(unattributed)"
        grouped.setdefault(str(key), Totals()).add(record)
    return grouped


def format_summary(records: list[CallRecord], by: str) -> str:
    grouped = summarize(records, by)
    if not grouped:
        return "No model calls recorded."
    width = max(len(key) for key in grouped)
    order = sorted(grouped.items(), key=lambda kv: (-kv[1].calls, kv[0]))
    lines = []
    for key, totals in order:
        line = (
            f"  {key.ljust(width)}  {totals.calls:>5} call(s)  "
            f"{totals.input_tokens:>9} in  {totals.output_tokens:>8} out"
            # Printed only where a provider reported it. A column of zeros
            # against providers that cannot tell would be the false-zero
            # this field exists to avoid.
            + (f"  {totals.hidden_output_tokens:>8} hidden" if totals.hidden_reported else "")
            + f"  {totals.cost:>10}"
        )
        if totals.errors:
            line += f"  ({totals.errors} failed)"
        lines.append(line)
    return "\n".join(lines)
