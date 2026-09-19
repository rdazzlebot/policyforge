"""The 45 CFR 170.315 parse, against real eCFR XML.

The fixture is 27 paragraphs lifted from eCFR's published § 170.315, not
written by hand, because the hazard here is entirely a property of the
regulation's shape. Each paragraph earns its place: all ten criterion
openers so the sequential rule has the full run to walk, `(i) [Reserved]`
because it must be seen and not emitted, the `(v)` and `(x)`
sub-paragraphs that a naive rule turns into criteria that do not exist, a
roman `(i)` so the same label resolves both ways inside one fixture, and
paragraphs carrying two and three inline levels.

**What makes this section different from 164 Subpart C:** the hierarchy is
not in the XML. It is one section of 540 flat `<P>` children whose nesting
lives in the text, so the parse reconstructs it from labels rather than
walking elements.

Nothing here reaches the network — the fetch is `test_ecfr_fetch.py`'s
question, and a parser test that needed eCFR to be up would be muted the
first week it was not.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from policyforge.ingest.onc_loader import (
    criteria_paragraphs,
    criterion_letters,
    is_reserved,
)

FIXTURE = Path(__file__).parent / "fixtures" / "ecfr_45cfr170_315_excerpt.xml"


@pytest.fixture(scope="module")
def paragraphs():
    return criteria_paragraphs(FIXTURE.read_text(encoding="utf-8"))


def test_the_criterion_letters_are_exactly_a_through_j(paragraphs):
    """Hand-checked against the regulation text at eCFR, 2026-09-16: §
    170.315 runs (a) Clinical, (b) Care coordination, (c) Clinical quality
    measures, (d) Privacy and security, (e) Patient engagement, (f) Public
    health, (g) Design and performance, (h) Transport methods, (i)
    [Reserved], (j) Modular API capabilities.

    Asserted as a set rather than a count, because a count passes on the
    wrong letters — which is exactly what the naive rule produces.
    """
    assert [letter for letter, _ in criterion_letters(paragraphs)] == list("abcdefghij")


def test_the_run_is_unbroken(paragraphs):
    """A gap would mean a real criterion was read as a sub-paragraph and
    dropped, which no other assertion here would catch."""
    letters = [letter for letter, _ in criterion_letters(paragraphs)]

    assert letters == [chr(ord("a") + index) for index in range(len(letters))]


def test_the_naive_rule_invents_criteria_that_do_not_exist(paragraphs):
    """The defect this module exists to prevent, pinned so nobody
    'simplifies' the sequential rule back into a regex.

    `^\\([a-z]\\)` reads every parenthesised letter as a criterion, so the
    Roman numerals `(v)` and `(x)` become `170.315(v)` and `170.315(x)`.
    Nothing crashes: the catalog loads and the controls look plausible.
    """
    naive = {match.group(1) for p in paragraphs if (match := re.match(r"^\(([a-z])\)\s", p))}
    sequential = {letter for letter, _ in criterion_letters(paragraphs)}

    assert {"v", "x"} <= naive, "the fixture must still contain the phantom-makers"
    assert not {"v", "x"} & sequential


def test_the_same_label_resolves_both_ways(paragraphs):
    """`(i)` is a criterion after `(h)` and a numeral everywhere else.

    Forty-seven paragraphs in the full section open with `(i)` and exactly
    one is a criterion. A parser that hardcoded either reading would pass a
    test that only ever saw the other one, so both appear here.
    """
    criteria = dict(criterion_letters(paragraphs))
    roman_paragraphs = [p for p in paragraphs if p.startswith("(i)") and p != criteria["i"]]

    assert "i" in criteria, "the criterion (i) must be found"
    assert roman_paragraphs, "and sub-paragraph (i)s must not be"


def test_the_reserved_criterion_is_identified(paragraphs):
    """`170.315(i)` is `[Reserved]`. It is found by the parse and must not
    be emitted as a control: a reserved criterion emitted is permanently
    unsatisfiable — it counts, it renders, it crosswalks, and it means
    nothing — so every coverage report after it carries a gap that can
    never close. The absence is asserted where the catalog is built; here
    the point is that the parse *sees* it rather than skipping it silently.
    """
    criteria = dict(criterion_letters(paragraphs))

    assert is_reserved(criteria["i"])
    assert not any(is_reserved(text) for letter, text in criteria.items() if letter != "i")


def test_the_lead_in_sentence_is_not_a_criterion(paragraphs):
    """The section opens with prose before `(a)`, and a rule that took the
    first paragraph as the first criterion would silently shift every
    letter by one."""
    assert paragraphs[0].startswith("The Secretary adopts")
    assert not paragraphs[0].startswith("(")
