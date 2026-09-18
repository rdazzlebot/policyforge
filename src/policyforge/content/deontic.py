"""How strongly a document states its requirements, and whether that
strength survived the trip from the control that justifies it.

An assessor does not read `must` and `should` as variations in tone. One is
a commitment the organization can be held to and the other is an intention,
and a Standard full of the second is not auditable. The source controls are
written in obligation language — 800-53 says an organization *shall* — so a
generated Standard that renders a cited requirement as "teams should
consider recertifying" has quietly downgraded a control while still
displaying its citation. The document looks correct, cites correctly, and
promises less than the framework it claims to satisfy.

That is the finding this module exists for, and it is narrower than
counting modal verbs. A `should` on its own is often right: a Policy states
principles, a Standard's commentary can advise, and flagging every one of
them would bury the case that matters under noise nobody reads — the same
trap `zardoz/answer.py` keeps warning about with its integrity checks.
What is reported is a sentence that carries a framework citation and does
not bind.

Deterministic on purpose. Every grader in this project is a substring, a
pattern or a rule, for the reason `evals/runner.py` gives: a checker that
needed a model would have the failure mode it exists to detect.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .tags import SOURCE_TAG_RE

#: A sentence binds the organization to something.
OBLIGATION = "obligation"
#: A sentence binds the organization *not* to something. Also binding.
PROHIBITION = "prohibition"
#: Advice. Real content, no commitment.
RECOMMENDATION = "recommendation"
#: Explicit latitude — the reader may choose.
PERMISSION = "permission"
#: A statement of fact, a heading, a definition.
NONE = "none"

#: Binding modalities. An assessor can ask for evidence against these and
#: nothing else.
BINDING = frozenset({OBLIGATION, PROHIBITION})

#: Framework citations, the same shape `edit/apply.py` protects when it
#: rewrites a page. A sentence carrying one is claiming to implement a
#: control, which is what makes its modality checkable at all. Decided in
#: `content/tags.py`, once, for every reader.
_CITATION_RE = SOURCE_TAG_RE

#: Ordered strongest first, because the longer forms contain the shorter
#: ones: "must not" must be tested before "must", or every prohibition in
#: the corpus reads as an obligation to do the thing it forbids.
_MODALITY_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        PROHIBITION,
        re.compile(
            r"\b(?:must not|shall not|may not|must never|shall never|"
            r"is prohibited|are prohibited|is forbidden|are forbidden)\b",
            re.IGNORECASE,
        ),
    ),
    (
        OBLIGATION,
        re.compile(
            r"\b(?:must|shall|is required to|are required to|is obligated to|"
            r"are obligated to|will be required to)\b",
            re.IGNORECASE,
        ),
    ),
    (
        RECOMMENDATION,
        re.compile(
            r"\b(?:should|ought to|is recommended|are recommended|"
            r"is encouraged|are encouraged|is advised|are advised)\b",
            re.IGNORECASE,
        ),
    ),
    (
        PERMISSION,
        re.compile(
            r"\b(?:may|can elect to|is permitted|are permitted|is allowed|"
            r"are allowed|at the discretion of|optional)\b",
            re.IGNORECASE,
        ),
    ),
)

#: Markdown emphasis, stripped before matching for the reason
#: `zardoz/answer.py` strips it: a generated Standard writes "**must**",
#: and a checker that cannot see through the asterisks reports the one
#: sentence that got it right.
_MARKUP_RE = re.compile(r"\*\*|__|\*|`")

_SENTENCE_RE = re.compile(r"[^.!?]+(?:[.!?]+|$)")


@dataclass(frozen=True)
class Statement:
    """One sentence, and what it commits the organization to."""

    line: int
    text: str
    modality: str
    cited: bool

    @property
    def binds(self) -> bool:
        return self.modality in BINDING

    @property
    def weakens_a_citation(self) -> bool:
        """Claims a control and promises less than one.

        A sentence with no citation is not making a claim this can judge,
        and a binding sentence has nothing wrong with it. The overlap is
        the finding.
        """
        return self.cited and not self.binds


def classify(sentence: str) -> str:
    """The strongest modality the sentence carries.

    Strongest rather than first, because real requirement prose nests
    latitude inside obligation: "records must be retained in written form
    (which may be electronic)" is an obligation with a permitted detail,
    not a permission. Reading it as the latter would report the firmest
    sentence in the document as its weakest.
    """
    visible = _MARKUP_RE.sub("", sentence)
    for modality, pattern in _MODALITY_PATTERNS:
        if pattern.search(visible):
            return modality
    return NONE


#: Markdown headings. Structure, not statements — "### 4.1 Media Protection"
#: commits the organization to nothing, and a heading ending in a numbered
#: section makes the sentence splitter cut in the middle of one.
_HEADING_LINE_RE = re.compile(r"^[ \t]*#{1,6}[ \t].*$", re.MULTILINE)


def analyze(text: str) -> list[Statement]:
    """Every sentence in `text`, classified, with the line it starts on.

    Headings are blanked rather than deleted so line numbers still point at
    the document a reader has open.

    A citation trailing its sentence on the following line is attached
    backwards. Generated Standards put it there — the requirement ends with
    a full stop and `[NIST MP-1 ...]` sits underneath — so a naive split
    makes the citation the opening of the *next* sentence, which is usually
    a heading and binds nothing. Left alone that reported every correctly
    cited requirement in the corpus as a weakened one, which is precisely
    the kind of false positive that teaches people to ignore the check.
    """
    text = _HEADING_LINE_RE.sub(lambda m: " " * len(m.group(0)), text)

    statements: list[Statement] = []
    for match in _SENTENCE_RE.finditer(text):
        raw = match.group(0)
        offset = match.start() + (len(raw) - len(raw.lstrip()))
        sentence = raw.strip()
        if not sentence:
            continue

        # Peel citations off the front and credit them to the sentence
        # above. The full stop lands *before* the citation, so a split puts
        # it at the head of whatever follows — which is either a heading
        # (binding nothing) or the next requirement (binding for its own
        # reasons, and wrongly absorbing this citation). Both readings lose
        # the link between a control and the sentence that implements it.
        trailing_citation = False
        while True:
            leading = _CITATION_RE.match(sentence)
            if not leading:
                break
            trailing_citation = True
            offset += leading.end()
            sentence = sentence[leading.end() :]
            stripped = sentence.lstrip(" \t\r\n.;:|")
            offset += len(sentence) - len(stripped)
            sentence = stripped

        if trailing_citation and statements:
            previous = statements[-1]
            statements[-1] = Statement(
                line=previous.line,
                text=previous.text,
                modality=previous.modality,
                cited=True,
            )

        if not sentence:
            continue

        statements.append(
            Statement(
                line=text.count("\n", 0, offset) + 1,
                text=" ".join(sentence.split()),
                modality=classify(sentence),
                cited=bool(_CITATION_RE.search(sentence)),
            )
        )
    return statements


def weakened_citations(text: str) -> list[Statement]:
    """Sentences that cite a control and do not bind."""
    return [s for s in analyze(text) if s.weakens_a_citation]


def binding_share(text: str) -> tuple[int, int]:
    """(binding sentences, sentences carrying any modality at all).

    The denominator excludes plain declaratives on purpose. A Standard is
    mostly prose — purpose, scope, definitions — and counting that as
    "unbound" would make every document look permissive.
    """
    modal = [s for s in analyze(text) if s.modality != NONE]
    return sum(1 for s in modal if s.binds), len(modal)
