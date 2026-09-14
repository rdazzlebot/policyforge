"""Runs a cheap model and falls back to a stronger one when the cheap model
demonstrably could not do the job.

The measurement this is built on: `deepseek-v4-flash` scores 92% routing,
100% resolution, 100% expansion at $0.0013 a sweep; `deepseek-v4-pro`
scores 97/100/100 at $0.0607, forty-seven times the price for one extra
routing case. Paying Pro rates for every call to cover the rare one is the
wrong trade, and so is never having Pro available.

**What counts as "could not do the job" is narrow on purpose.** Only
`ReasoningBudgetExhausted` escalates by default: the model spent its whole
budget deliberating, twice, and never began an answer. That is a fact the
provider layer can see for itself, unambiguously, without knowing anything
about the task.

Everything more interesting than that — a wrong routing decision, an answer
citing a passage it should not, an unfilled placeholder reproduced as fact
— is invisible here, and deliberately so. `LLMProvider.generate()` receives
a system prompt, a user prompt and a budget; it never sees the passages,
so it cannot run `zardoz/answer.py`'s integrity checks. A cascade gated on
*those* belongs in `answer_question`, which holds the question, the
passages, the provider and the verdict at once. It is a separate piece of
work and is on the roadmap. This one is the floor, not the ceiling.

Nothing is hidden. The `LLMResponse.model` of an escalated call names the
model that actually answered, so a caller can always tell which one it got.
"""

from __future__ import annotations

from ._inline_thinking import ReasoningBudgetExhausted
from .base import LLMProvider, LLMResponse

#: Failures that mean "this model could not produce an answer", as opposed
#: to "this model produced a bad answer" (invisible here) or "the request
#: never ran" (a rate limit or a dead key, which the stronger model would
#: hit too — escalating those would double the bill to fail twice).
ESCALATE_ON: tuple[type[Exception], ...] = (ReasoningBudgetExhausted,)


class CascadeProvider(LLMProvider):
    """Tries `primary`, falls back to `escalate_to` on a recoverable failure.

    Both are ordinary providers, so a cascade can pair any two models —
    local and hosted, cheap and strong, or two vendors for redundancy.
    """

    def __init__(
        self,
        *,
        primary: LLMProvider,
        escalate_to: LLMProvider,
        escalate_on: tuple[type[Exception], ...] = ESCALATE_ON,
    ):
        self._primary = primary
        self._escalate_to = escalate_to
        self._escalate_on = escalate_on
        #: Counters, so a run can report how often the cheap model sufficed.
        #: The whole economic case rests on that ratio being high, and an
        #: unmeasured cascade is one nobody can tell is working.
        self.primary_calls = 0
        self.escalations = 0

    @property
    def model(self) -> str:
        """What this provider is, for anything that logs a model name."""
        return (
            f"{getattr(self._primary, 'model', '?')} -> {getattr(self._escalate_to, 'model', '?')}"
        )

    def generate(
        self,
        *,
        system: str,
        prompt: str,
        max_tokens: int = 4096,
        temperature: float = 0.2,
    ) -> LLMResponse:
        self.primary_calls += 1
        try:
            return self._primary.generate(
                system=system, prompt=prompt, max_tokens=max_tokens, temperature=temperature
            )
        except self._escalate_on:
            self.escalations += 1

        # Outside the `except` so that a failure of the stronger model is
        # reported on its own terms rather than chained to the first one.
        # "Pro also ran out of room" is the useful message; "Pro failed
        # while handling Flash failing" buries it.
        return self._escalate_to.generate(
            system=system, prompt=prompt, max_tokens=max_tokens, temperature=temperature
        )

    def supports_schema(self) -> bool:
        """Only when *both* halves can honour one.

        An escalation has to be able to answer the same question in the
        same shape. A cascade that constrained the cheap model and then
        fell back to unconstrained prose would hand the caller JSON most of
        the time, which is worse than never promising it.
        """
        return self._primary.supports_schema() and self._escalate_to.supports_schema()

    def generate_json(self, **kwargs) -> LLMResponse:
        self.primary_calls += 1
        try:
            return self._primary.generate_json(**kwargs)
        except self._escalate_on:
            self.escalations += 1
        return self._escalate_to.generate_json(**kwargs)

    def check(self) -> bool:
        """Both halves must work.

        Checking only the primary would report a healthy cascade whose
        fallback has a dead key, and the first thing that discovers it
        would be a hard question in front of a user.
        """
        return self._primary.check() and self._escalate_to.check()
