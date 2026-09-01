"""Turning retrieved passages into an answer somebody can act on.

The rule this module exists to enforce is that **every claim carries a
citation, or it does not get made**. Not because citations are tidy, but
because of who reads the output: somebody deciding whether their
organization is doing what its own policy requires. A confidently wrong
answer there is worse than silence, since silence sends them to read the
document and a wrong answer stops them.

Three things follow from that, and all three are in the code rather than in
the prompt, because a prompt is a request and a check is a guarantee:

* **No passages, no request.** When retrieval finds nothing, the model is
  never called. There is nothing to ground an answer in, and a model asked
  a question with no context will answer it from its own knowledge of what
  access control standards usually say — which is exactly the failure this
  package is built to prevent, and it arrives sounding entirely plausible.
* **Citations are verified after the fact.** The model is told to cite
  every claim; it is not trusted to have done so. A marker pointing at a
  passage that was never supplied is a fabricated citation, and it is
  caught here rather than by the reader.
* **Quotations are checked against the source text.** A quoted requirement
  that does not appear verbatim in the passage it cites is the single most
  damaging output this tool could produce, because a quotation is what
  someone pastes into a ticket or shows an assessor.

None of these makes the model honest. They make dishonesty visible, which
is the most a caller of an API can actually do.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .retrieve import Passage

#: What the model is told to return when the passages do not answer the
#: question. A sentinel rather than a phrase to pattern-match, because
#: "the documents do not say" and "the documents don't appear to specify"
#: are the same answer and no regex should have to know that.
REFUSAL_SENTINEL = "INSUFFICIENT_CONTEXT"

#: Quoted spans shorter than this are not checked for verbatim fidelity.
#: Models use quotes for mention as well as quotation — the "Owner" field,
#: a "trusted" document — and flagging those would train the reader to
#: ignore the warning that matters.
MIN_QUOTE_CHARS = 25

_CITATION_RE = re.compile(r"\[(\d+)\]")
_QUOTE_RE = re.compile(rf"[\"“]([^\"”]{{{MIN_QUOTE_CHARS},}})[\"”]")

SYSTEM_PROMPT = """You answer questions about an organization's own \
information-security policy documents, using only the passages you are given.

Rules, in priority order:

1. Ground every claim. Each sentence that states what the documents require,
   permit, or forbid must end with a citation marker naming the passage it
   came from: [1], [2], or [1][3] where two passages support it. A sentence
   with no marker is not allowed unless it is a direct answer to the
   question that the markers on adjacent sentences already support.
2. Never use knowledge from outside the passages. You know a great deal
   about what access control standards usually say. That knowledge is
   wrong here: the question is what *these* documents say, and a plausible
   requirement this organization has not actually written down is the worst
   thing you can produce.
3. If the passages do not answer the question, reply with exactly
   INSUFFICIENT_CONTEXT and nothing else. Do not partially answer, do not
   hedge into an answer, and do not explain what the documents do cover
   instead. A question that cannot be answered from the documents has one
   correct response and this is it.
4. Quote exactly or not at all. Any text you put in quotation marks must
   appear verbatim in the passage you cite. If you cannot reproduce it
   exactly, paraphrase it without quotation marks.
5. Where passages disagree, say so and cite both rather than choosing.
   Two documents contradicting each other about a requirement is a finding
   in its own right, and resolving it silently hides it.
6. Answer in plain prose. No preamble, no restatement of the question, no
   offer to help further. Two or three sentences is usually right; these
   are people checking one fact, not reading an essay.
7. A passage marked `supporting` has no declared owner. You may use it, but
   say that it is unowned when you do — a requirement nobody is accountable
   for is a different kind of fact from one a named team owns."""


@dataclass
class Answer:
    """A grounded answer, and everything needed to distrust it."""

    text: str
    passages: list[Passage] = field(default_factory=list)
    #: Passage numbers the answer actually cited, in the order first cited.
    cited: list[int] = field(default_factory=list)
    #: True when there was nothing to answer from, or the model said the
    #: passages do not answer the question. Not a failure — an outcome.
    refused: bool = False
    #: Integrity problems found after the model replied. Never silently
    #: repaired: a caller that hides these is worse than no checking at all,
    #: because it produces the same output while looking safer.
    warnings: list[str] = field(default_factory=list)

    @property
    def is_grounded(self) -> bool:
        return bool(self.cited) and not self.warnings

    def sources(self) -> list[tuple[int, Passage]]:
        """The cited passages, numbered as the answer refers to them."""
        return [(n, self.passages[n - 1]) for n in self.cited if 1 <= n <= len(self.passages)]


def format_passages(passages: list[Passage]) -> str:
    """Number the passages for the model exactly as the answer will cite them."""
    blocks = []
    for number, passage in enumerate(passages, start=1):
        confidence = "trusted" if passage.is_trusted else "supporting (no declared owner)"
        owner = passage.document.owner or "unassigned"
        blocks.append(
            f"[{number}] {passage.document.title}"
            f"{' § ' + passage.chunk.section if passage.chunk.section else ''}\n"
            f"    owner: {owner} | {confidence}\n"
            f"---\n{passage.chunk.text.strip()}\n---"
        )
    return "\n\n".join(blocks)


def build_prompt(question: str, passages: list[Passage]) -> str:
    return (
        f"PASSAGES\n\n{format_passages(passages)}\n\n"
        f"QUESTION\n\n{question.strip()}\n\n"
        "Answer from the passages above, citing each claim. If they do not "
        f"answer the question, reply with exactly {REFUSAL_SENTINEL}."
    )


def check_answer(text: str, passages: list[Passage]) -> tuple[list[int], list[str]]:
    """Verify an answer against the passages it was built from.

    Returns `(cited passage numbers, warnings)`. Everything here is a check
    the model was already asked to satisfy in the prompt — asked, and then
    verified, because those are different things.
    """
    warnings: list[str] = []

    cited: list[int] = []
    for marker in _CITATION_RE.findall(text):
        number = int(marker)
        if number not in cited:
            cited.append(number)

    invented = [n for n in cited if not 1 <= n <= len(passages)]
    if invented:
        warnings.append(
            f"cites passage(s) {', '.join(f'[{n}]' for n in invented)}, which were never "
            f"supplied — only [1]-[{len(passages)}] exist"
        )

    if not cited:
        warnings.append("makes claims without citing any passage")

    # A quotation is what somebody pastes into a ticket. If it is not
    # verbatim, that is the most damaging thing this tool could emit.
    haystack = " ".join(" ".join(p.chunk.text.split()) for p in passages)
    for quote in _QUOTE_RE.findall(text):
        if " ".join(quote.split()) not in haystack:
            excerpt = quote if len(quote) <= 60 else quote[:60] + "..."
            warnings.append(f'quotes text that appears in no passage: "{excerpt}"')

    return cited, warnings


def answer_question(
    question: str,
    passages: list[Passage],
    provider,
    *,
    max_tokens: int = 1024,
) -> Answer:
    """Answer `question` from `passages`, or decline to.

    `provider` is only reached when there is something to ground an answer
    in. Temperature is zero: the same question over the same documents
    should not give two different accounts of what the organization
    requires, and there is no part of this task that benefits from variety.
    """
    if not passages:
        return Answer(
            text=(
                "Nothing in the synced documents appears to bear on that. That may be "
                "the answer, or the document you want may not be synced — /corpus shows "
                "what is."
            ),
            refused=True,
        )

    response = provider.generate(
        system=SYSTEM_PROMPT,
        prompt=build_prompt(question, passages),
        temperature=0.0,
        max_tokens=max_tokens,
    )
    text = response.text.strip()

    if REFUSAL_SENTINEL in text:
        return Answer(
            text=(
                "The documents I have do not answer that. The passages below came "
                "closest, but none of them says it."
            ),
            passages=passages,
            refused=True,
        )

    cited, warnings = check_answer(text, passages)
    return Answer(text=text, passages=passages, cited=cited, warnings=warnings)
