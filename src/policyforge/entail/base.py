"""Does the cited passage actually support the claim?

`zardoz/answer.py` verifies everything about an answer that can be decided
by looking: the citation points at a passage that exists, the quotation is
verbatim, no interval appears that no passage states, no placeholder is
presented as a value, no unowned source goes undisclosed. All of it is a
pattern or a comparison, and all of it is exact.

None of it can answer the remaining question. Given a passage that says
*"IT Asset Management shall generate and retain Certificates of
Destruction"*, the sentence *"The Security Officer approves Certificates of
Destruction. [1]"* cites correctly, quotes nothing, invents no interval and
names no placeholder — and is wrong about both the actor and the act. Every
deterministic check passes it. That is the gap, and it is the failure mode
an assessor would notice first.

**This is a model judging a model, and that is a real cost.**
`evals/runner.py` refuses it for grading, with a reason that holds: *"A
grader that itself needed a model would have the failure mode it exists to
detect."* Today's runs bear it out — the deterministic checks caught
sonnet-5 fabricating a quotation. So three lines are drawn here and none of
them should be crossed casually:

1. **`check_answer` is not touched.** It stays pure, exact, and dependency
   free. Its warnings remain facts.
2. **These findings are opinions, and are labelled as such.** Mixing a
   model's judgement into a list of verified facts would devalue the facts,
   which are the more useful half.
3. **This is never an eval grader.** The harness keeps deciding with
   patterns, or it stops being able to measure the thing it exists for.

The strongest version of this uses a dedicated NLI cross-encoder —
DeBERTa-MNLI and its relatives — which is small, fast, and crucially from a
different model family than whatever wrote the answer. That independence is
most of the value. It needs PyTorch, which on this project's Windows/AMD
target means CPU-only and a heavy dependency, so `llm_entailer.py` ships
first and the interface leaves room for the better one.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass

#: The passage supports the claim.
ENTAILED = "entailed"
#: The passage neither supports nor contradicts it — the common failure.
#: A claim about an actor the passage never mentions lands here.
NEUTRAL = "neutral"
#: The passage says otherwise. Rarer and worse.
CONTRADICTED = "contradicted"

_CITATION_RE = re.compile(r"\[(\d+)\]")
_SENTENCE_RE = re.compile(r"[^.!?]+(?:[.!?]+|$)")


@dataclass(frozen=True)
class Verdict:
    """One judgement, and why."""

    label: str
    #: Free text from the judge. Kept because "the passage names IT Asset
    #: Management, not the Security Officer" is what makes a finding
    #: actionable, and a bare label is not.
    reason: str = ""

    @property
    def supports(self) -> bool:
        return self.label == ENTAILED


@dataclass(frozen=True)
class Unsupported:
    """A sentence whose cited passages do not carry it."""

    sentence: str
    cited: list[int]
    verdict: Verdict

    def __str__(self) -> str:
        markers = "".join(f"[{n}]" for n in self.cited)
        detail = f" — {self.verdict.reason}" if self.verdict.reason else ""
        return f"{self.verdict.label} by {markers}: {self.sentence!r}{detail}"


class Entailer(ABC):
    """Judges whether a premise supports a hypothesis."""

    @abstractmethod
    def entails(self, premise: str, hypothesis: str) -> Verdict:
        raise NotImplementedError

    @abstractmethod
    def check(self) -> bool:
        """Cheap round-trip."""
        raise NotImplementedError


def cited_sentences(text: str, count: int) -> list[tuple[str, list[int]]]:
    """(sentence, cited passage numbers) for each sentence that cites one.

    The citation follows the full stop — "…destruction. [1]" — so a naive
    split puts the marker at the head of the *next* sentence and leaves the
    claim uncited. Judged that way the model is handed "[1]" and nothing
    else, and replies, reasonably, that no claim was supplied. The same
    trailing-citation shape bit `content/deontic.py`; it is a property of
    how this project's answers are written, not a quirk of one module.
    """
    pairs: list[tuple[str, list[int]]] = []
    for match in _SENTENCE_RE.finditer(text or ""):
        segment = match.group(0).strip()
        if not segment:
            continue

        leading: list[int] = []
        while True:
            found = _CITATION_RE.match(segment)
            if not found:
                break
            leading.append(int(found.group(1)))
            # lstrip() with no argument covers every whitespace form,
            # which avoids spelling control characters in a literal.
            segment = segment[found.end() :].lstrip().lstrip(".;:|")

        if leading and pairs:
            sentence, cited = pairs[-1]
            pairs[-1] = (sentence, list(dict.fromkeys(cited + leading)))

        if not segment:
            continue
        inline = [int(n) for n in _CITATION_RE.findall(segment)]
        pairs.append((" ".join(_CITATION_RE.sub("", segment).split()), list(dict.fromkeys(inline))))

    return [
        (sentence, [n for n in cited if 1 <= n <= count])
        for sentence, cited in pairs
        if sentence and [n for n in cited if 1 <= n <= count]
    ]


def unsupported_claims(text: str, passages: list, entailer: Entailer) -> list[Unsupported]:
    """Cited sentences that their own passages do not support.

    Only sentences carrying a citation are judged. One with no citation is
    already `check_answer`'s business — it reports "makes claims without
    citing any passage" — and judging it here would duplicate a finding
    that is a fact with one that is an opinion.

    A sentence citing several passages is supported if *any* of them
    carries it, because an answer is allowed to draw one claim from two
    documents and citing both is the behaviour the prompt asks for.
    """
    findings: list[Unsupported] = []
    for sentence, cited in cited_sentences(text, len(passages)):
        verdicts = [entailer.entails(passages[n - 1].chunk.text, sentence) for n in cited]
        if any(v.supports for v in verdicts):
            continue
        # Report the most specific complaint available: a contradiction is
        # a stronger finding than "says nothing about it", and burying it
        # behind a neutral verdict from a second passage would hide it.
        worst = next((v for v in verdicts if v.label == CONTRADICTED), verdicts[0])
        findings.append(Unsupported(sentence=sentence, cited=cited, verdict=worst))
    return findings


def get_entailer(config: dict) -> Entailer | None:
    """Build the configured entailer, or None when there isn't one.

    None is the normal case. This is an addition, and one with a cost worth
    opting into deliberately rather than inheriting.
    """
    block = config.get("entail")
    if not block:
        return None

    provider = block.get("provider", "llm")
    if provider == "llm":
        from .llm_entailer import LLMEntailer, entailment_provider

        model = block.get("model")
        return LLMEntailer(
            model=model,
            max_tokens=block.get("max_tokens", 2000),
            # Left to LLMEntailer to refuse a missing model, with the reason
            # it has to be a different one from the answerer's.
            provider=entailment_provider(block, config) if model else None,
        )

    raise ValueError(f"Unknown entail.provider '{provider}'. Supported: llm.")
