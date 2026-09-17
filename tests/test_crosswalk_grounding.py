"""A quote is grounded when its words are the text's words, in order.

Each accepting case is a shape measured from real model output on the HIPAA
probe; each refusing case is what the check exists to stop.
"""

from __future__ import annotations

import pytest

from policyforge.crosswalk.grounding import grounded, is_whole_text

SI_3 = (
    "Malicious Code Protection a. Implement [Selection (one or more): signature based; "
    "non-signature based] malicious code protection mechanisms at system entry and exit "
    "points to detect and eradicate malicious code;"
)
SC_8 = (
    "Transmission Confidentiality and Integrity Protect the [Selection (one or more): "
    "confidentiality; integrity] of transmitted information."
)


@pytest.mark.parametrize(
    ("quote", "text"),
    [
        ("malicious code protection mechanisms at system entry and exit points", SI_3),
        # Parameter brackets read aloud.
        ("Implement signature based malicious code protection mechanisms", SI_3),
        ("Protect the confidentiality; integrity of transmitted information", SC_8),
        # Parameter brackets dropped.
        ("Protect the of transmitted information", SC_8),
        # Two clauses joined by an ellipsis, in the text's order.
        ("malicious code protection mechanisms ... detect and eradicate malicious code", SI_3),
        ("malicious code protection mechanisms … detect and eradicate malicious code", SI_3),
        # Case and punctuation differ.
        ("MALICIOUS CODE PROTECTION MECHANISMS, at system entry", SI_3),
    ],
)
def test_a_real_quote_is_grounded(quote, text):
    assert grounded(quote, text)


@pytest.mark.parametrize(
    "quote",
    [
        "Implement multifactor authentication for privileged remote access",
        "code protection malicious implement mechanisms",
        "detect and eradicate malicious code ... malicious code protection mechanisms",
        # A fragment too short to prove anything, carried by a long one.
        "Implement ... malicious code protection mechanisms at system entry",
        "malicious code",
        "",
    ],
)
def test_a_fabricated_reordered_or_thin_quote_is_not(quote):
    assert not grounded(quote, SI_3)


def test_a_whole_short_specification_can_be_quoted_and_only_whole():
    spec = "Periodic security updates."
    assert is_whole_text("Periodic security updates.", spec)
    assert not is_whole_text("security updates", spec)
    assert not grounded("security updates", f"Security reminders {spec}")


def test_an_empty_specification_has_no_whole_to_quote():
    """The one-word quote the old minimum let through by counting an empty text."""
    assert not is_whole_text("Implementation", "")
    assert not grounded("Implementation", "Implementation specifications")


# The examples the matcher's docstring promises, which the first version failed:
# a miss moved the search to the end of its window and every later word missed.


def test_a_dropped_article_in_the_quote_still_matches():
    """The text has a word the quote leaves out."""
    assert grounded("implement malicious code protection mechanisms at entry and exit points", SI_3)


def test_an_inserted_word_in_the_quote_still_matches():
    """The quote has a word the text lacks, and the rest still count."""
    assert grounded("malicious code protection mechanisms and at system entry", SI_3)
    assert grounded("the malicious code protection mechanisms at system entry", SI_3)


def test_a_short_fragment_may_not_miss_a_word():
    """Under six words, one missing word is a sixth of the evidence or more."""
    assert not grounded("malicious code and protection mechanisms", SI_3)


def test_two_inserted_words_in_a_short_quote_are_refused():
    assert not grounded("malicious foo code bar protection mechanisms at entry", SI_3)
