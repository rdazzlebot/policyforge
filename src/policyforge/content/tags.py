"""What a framework source tag looks like, decided once.

A generated document carries its traceability inline, as bracketed tags
after the sentence that implements a control: `[NIST AC-2 | HIPAA
164.308(a)(3)(i)]`. Four places read them — the edit path, to refuse a
revision that dropped one; `check`, to report a tag the synthesis carries
and the document lost; `frameworks/drift`, to find the documents a changed
control reaches; and the deontic analysis, to know which sentences claim to
implement something. Each had its own copy of the pattern, and every copy
was a hand-written list of framework names.

A list is the wrong shape for this. The names in a tag are chosen by the
model at generation time, by example rather than by rule, and the bundled
starter set already carries `[ARC PE-1 ...]` where the list said
`ARC-AMPE`: twenty-two tags that every one of those readers looked straight
through. `check` could not report them dropped, drift could not reach the
documents that cite them, and the counts `satisfies` prints were a floor
that said so in its docstring. Adding `ARC` to four lists fixes the tags
seen today and none of the tags a new catalog, or a model with a different
habit, writes tomorrow.

So a tag is recognised by its shape, not by a roll call:

* it opens with a framework name — one or more capitalised tokens
  (`NIST`, `ARC-AMPE`, `HIPAA Security Rule`);
* the name is followed by a requirement identifier, which is any token
  carrying a digit (`AC-2`, `164.308(a)`, `01.a`, `800-53`);
* it is not a wikilink and not the text of a markdown link.

The identifier rule is what keeps prose out. `[NIST AI RMF alignment]` and
`[NIST CAVP]` occur in this repository's own documents and were matched by
the old list as citations, which they are not; a name with nothing
number-shaped after it is a phrase in brackets. Measured over every text in
the repository before this shipped: the shape matches every tag the list
matched, adds none, and drops exactly those six phrases.

Which catalog a name points at is a separate question, answered by
`topics/satisfies.resolve_framework` against the catalogs actually loaded;
this module only says what is a tag.

One trap, named because it cost two reviewers an hour each. A placeholder
whose label opens with a framework name — `[HIPAA Documentation Review
Frequency]`, sitting mid-sentence beside `[Ticketing System]` and
`[Contract Repository]`, standing in for a value nobody has decided — looks
like a citation to anyone reasoning about its form, and the old list
counted it as one because `HIPAA` was on the list. It is not a citation:
the step it sits in is cited by its own heading, `[HIPAA 164.316(b)(1) |
...]`, and the three scans that published it as the corpus's least
followable citation were counting a placeholder. The identifier rule is
what tells the two apart, and it is the only thing that does — backticks
do not, since a few real tags in generated documents are backticked too.
So the rule is: a name with nothing number-shaped after it is a phrase in
brackets, in generated content as much as in prose, and a reader who wants
it reported as something else should first go and read it in its document.
"""

from __future__ import annotations

import re

#: A name token: a capital, letters, hyphenated letters, optionally ending in
#: digits (`NIST`, `ARC-AMPE`, `GovRAMP`, `SOC2`). A hyphen followed by a
#: digit is what an identifier looks like (`PE-1`, `800-53`), so it ends the
#: name rather than extending it, which is what lets `framework_name` stop
#: at `ARC` in `[ARC PE-1 ...]`.
_NAME_WORD = r"[A-Z][A-Za-z]*(?:-[A-Za-z]+)*\d*"
_NAME = rf"{_NAME_WORD}(?: {_NAME_WORD})*"

#: One framework source tag, whole. No capturing group, on purpose: every
#: reader calls `findall` and expects the tag as written, and a group would
#: quietly turn that into the framework name alone.
SOURCE_TAG_RE = re.compile(
    r"(?<!\[)\[(?!\[)"  # an opening bracket, not part of a `[[wikilink]]`
    rf"(?:{_NAME})"  # capitalised name tokens
    r"\s+(?=[^\]\s]*\d)"  # then a token carrying a digit: the requirement id
    r"[^\]]*\]"  # the rest of the tag
    r"(?!\()"  # and not `[text](url)`
)

_LEADING_NAME_RE = re.compile(rf"\[({_NAME})(?:\s|\])")


def source_tags(text: str) -> list[str]:
    """Every source tag in `text`, in order, as written."""
    return SOURCE_TAG_RE.findall(text)


def framework_name(tag: str) -> str:
    """The framework a tag opens with, as written: `ARC` in `[ARC PE-1 | ...]`.

    As written, not resolved: which catalog `ARC` names is
    `topics/satisfies.resolve_framework`'s question.
    """
    match = _LEADING_NAME_RE.match(tag)
    return match.group(1) if match else ""
