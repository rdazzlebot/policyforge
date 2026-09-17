"""Whether a quote a model gave is really in the text it quoted.

A proposed mapping carries two quotes — the words of the requirement it
addresses and the words of the control that address them — and a mapping
whose quotes are not in the texts is refused before anybody reviews it. The
quotes are what a reviewer reads instead of both documents, so a quote the
text does not contain would put a fabricated reason in front of the person
deciding.

Exact substring matching was the first version, and measured on 75 HIPAA
requirements it refused 73 mappings, most of them right. SP 800-53 writes
its parameters as `[Selection (one or more): confidentiality; integrity]`,
and a model quoting that control writes "protect the confidentiality and
integrity", which is the text read aloud rather than a fabrication. Models
also join two clauses with an ellipsis. So matching is over words, in
order: bracketed parameter syntax is set aside, a few missing or inserted
words are tolerated, and an ellipsis splits a quote into fragments that must
each be found, in order. What stays refused is what matters — words the text
does not contain, or its words out of order.
"""

from __future__ import annotations

import re

_PARAMETER = re.compile(r"\[(?:Assignment|Selection)[^\]]*\]", re.IGNORECASE)
_WORD = re.compile(r"[a-z0-9]+")
_ELLIPSIS = re.compile(r"\.\.\.|…")

#: Share of a fragment's words that must be found, in order, for it to count.
COVERAGE = 0.85
#: A fragment of fewer words than this proves little on its own, so a quote
#: built from several must give each at least this many.
MIN_FRAGMENT_WORDS = 3
#: The usual minimum for a whole quote. `grounded` lowers it for a source text
#: shorter than this: HIPAA's "Periodic security updates." is the whole
#: specification, and it cannot be quoted in four words.
MIN_QUOTE_WORDS = 4


def words(text: str, *, drop_parameters: bool = False) -> list[str]:
    if drop_parameters:
        text = _PARAMETER.sub(" ", text)
    return _WORD.findall(text.lower())


def _match_after(fragment: list[str], tokens: list[str], start_at: int) -> int:
    """Index just past `fragment` found in order in `tokens`, or -1.

    Gaps are allowed within a window of twice the fragment's length, so a
    dropped article or an inserted "and" does not fail a real quote, and a
    fragment spread thinly across a paragraph does.
    """
    needed = COVERAGE * len(fragment)
    for start in range(start_at, len(tokens)):
        if tokens[start] != fragment[0]:
            continue
        found, i = 1, start + 1
        limit = min(start + 2 * len(fragment), len(tokens))
        for word in fragment[1:]:
            while i < limit and tokens[i] != word:
                i += 1
            if i < limit:
                found += 1
                i += 1
        if found >= needed:
            return i
    return -1


def grounded(quote: str, text: str, *, min_words: int = MIN_QUOTE_WORDS) -> bool:
    """Whether `quote` is words of `text`, in order."""
    fragments = [words(f, drop_parameters=True) for f in _ELLIPSIS.split(quote)]
    fragments = [f for f in fragments if f]
    if not fragments or sum(len(f) for f in fragments) < min_words:
        return False
    if len(fragments) > 1 and any(len(f) < MIN_FRAGMENT_WORDS for f in fragments):
        return False
    # Against the text both without and with its parameter brackets: a model
    # may read the brackets aloud or quote their contents.
    for tokens in (words(text, drop_parameters=True), words(text)):
        position = 0
        for fragment in fragments:
            position = _match_after(fragment, tokens, position)
            if position < 0:
                break
        if position >= 0:
            return True
    return False


def minimum_for(requirement_text: str) -> int:
    """The shortest quote to accept from a requirement this long."""
    return max(1, min(MIN_QUOTE_WORDS, len(words(requirement_text))))
