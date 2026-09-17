"""A quote is grounded when its words are the text's words, in order.

Each accepting case is a shape measured from real model output on the HIPAA
probe; each refusing case is what the check exists to stop.
"""

from __future__ import annotations

import pytest

from policyforge.crosswalk.grounding import grounded, minimum_for

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


def test_a_whole_short_specification_can_be_quoted():
    spec = "Periodic security updates."
    assert grounded("Periodic security updates.", spec, min_words=minimum_for(spec))
    assert not grounded("security updates", spec, min_words=minimum_for(spec))


def test_the_minimum_is_the_usual_four_for_anything_longer():
    assert minimum_for("Implement procedures for terminating access to electronic PHI.") == 4
