"""42 CFR Part 2, read into sections.

The fixture is six real sections cut from the 2026-09-17 revision, chosen
for the cases a parser has to get right rather than for being the first
six: the security hub (2.16), a control-shaped section with a conduct
heading (2.19), a section whose security duty is a cross-reference (2.52),
the definitions section that must be dropped (2.11), the statutory
authority section that must also be dropped (2.1), and one pure conduct
section (2.13).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from policyforge.ingest.part2_loader import (
    EXPECTED_SECTIONS,
    SECTION_ID_RE,
    Section,
    sections,
)

FIXTURE = Path(__file__).parent / "fixtures" / "ecfr_42cfr2_excerpt.xml"


@pytest.fixture(scope="module")
def excerpt() -> str:
    return FIXTURE.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def parsed(excerpt) -> list[Section]:
    return sections(excerpt, strict=False)


# --------------------------------------------------------------------------
# The id pattern, which is where a copied parser fails silently
# --------------------------------------------------------------------------


def test_the_section_pattern_matches_how_this_part_actually_numbers():
    """`2.1` through `2.68`: one or two digits after the dot."""
    for number in ("2.1", "2.4", "2.11", "2.16", "2.19", "2.31", "2.52", "2.68"):
        assert SECTION_ID_RE.match(number), number


def test_part_171_s_pattern_matches_nothing_here():
    """The near miss this parser exists downstream of.

    Part 171 numbers its sections `171.203`, `171.1000` — three or four
    digits. Copied across, the pattern does not merely look wrong, it
    matches **zero** of Part 2's sections, and a catalog built on it comes
    out empty while every check that asks whether its entries are
    well-formed passes on the nothing.
    """
    borrowed = re.compile(r"^171\.\d{3,4}$")

    matched = [n for n in ("2.1", "2.11", "2.16", "2.19", "2.52", "2.68") if borrowed.match(n)]

    assert matched == []


def test_a_deeper_number_is_not_a_section(parsed):
    """`2.16(a)` is a paragraph within a section, not a section."""
    assert not SECTION_ID_RE.match("2.16(a)")
    assert not SECTION_ID_RE.match("2.311")


# --------------------------------------------------------------------------
# An empty or short parse is loud
# --------------------------------------------------------------------------


def test_a_parse_that_finds_nothing_refuses_rather_than_returning_empty():
    """An empty catalog is the failure mode that passes every other check,
    so it is the one checked explicitly."""
    with pytest.raises(ValueError) as caught:
        sections("<DIV5><DIV8 N='171.203'><HEAD>Security exception.</HEAD></DIV8></DIV5>")

    message = str(caught.value)
    assert "matched 0 of the 1 sections" in message
    assert "parser fault" in message, "an empty parse must be named a parser fault, not a change"
    assert "171.203" in message, "the message must name the section the pattern missed"


def test_the_primary_count_check_asks_the_document_not_the_constant():
    """**The check that catches a wrong pattern uses no hand-written
    number.** Both sides come from the XML: what eCFR says is there, and
    what the pattern matched. A constant nobody can re-derive is the same
    shape as a hand-written prefix list — right the day it is written and
    unverifiable after.

    Pinned with a document whose section count is *not* `EXPECTED_SECTIONS`
    and not zero, so passing it cannot be an accident of either number.
    """
    three_unmatched = (
        "<DIV5>"
        + "".join(f"<DIV8 N='171.{n}'><HEAD>x</HEAD></DIV8>" for n in (203, 204, 205))
        + "</DIV5>"
    )

    with pytest.raises(ValueError) as caught:
        sections(three_unmatched)

    message = str(caught.value)
    assert "matched 0 of the 3 sections" in message
    assert str(EXPECTED_SECTIONS) not in message, "the pattern check must not cite the constant"


def test_a_document_the_pattern_fully_matches_is_still_held_to_the_pinned_count(excerpt):
    """The second check, for the failure the first cannot see: a response
    that is internally consistent and is not the whole part. Six sections
    all match the pattern, so only the pinned count can catch it."""
    with pytest.raises(ValueError) as caught:
        sections(excerpt)

    message = str(caught.value)
    assert f"expected {EXPECTED_SECTIONS}" in message
    assert "the pattern is fine" in message
    assert "truncated" in message
    assert "2.16" in message, "the message should name what it did find"


def test_the_count_check_is_the_only_thing_strict_turns_off(excerpt, parsed):
    """`strict=False` parses an excerpt. It must not also relax the id
    pattern, or a fixture would prove less than it appears to."""
    assert len(parsed) == 6
    assert all(SECTION_ID_RE.match(s.number) for s in parsed)


# --------------------------------------------------------------------------
# What a section carries
# --------------------------------------------------------------------------


def test_the_heading_loses_its_section_symbol_and_number(parsed):
    by_number = {s.number: s for s in parsed}

    assert by_number["2.16"].title == "Security for records and notification of breaches."
    assert by_number["2.19"].title == "Disposition of records by discontinued programs."


def test_italic_runs_inside_a_paragraph_are_kept(parsed):
    """eCFR names paragraphs in `<I>` runs — "Requirements for formal
    policies and procedures" is one — and reading `.text` alone truncates
    at the first, which loses content while still producing a section."""
    security = next(s for s in parsed if s.number == "2.16")

    assert "Requirements for formal policies and procedures" in security.text


def test_the_security_section_carries_its_actual_obligations(parsed):
    """Verified against the fetched text rather than the heading. If this
    section ever stops saying these things, the product judgement that
    Part 2 contains one crosswalkable control stops being true."""
    security = next(s for s in parsed if s.number == "2.16")

    for duty in (
        "formal policies and procedures",
        "sanitizing the hard copy media",
        "secure room, locked file cabinet",
        "45 CFR 164.514(b)",
        "subpart D of 45 CFR part 164",
    ):
        assert duty in security.text, duty


# --------------------------------------------------------------------------
# Vocabulary is not a requirement
# --------------------------------------------------------------------------


def test_definitions_and_statutory_authority_state_no_obligation(parsed):
    """Dropped for `hipaa_loader`'s reason: a defined term is not a duty."""
    by_number = {s.number: s for s in parsed}

    assert not by_number["2.11"].states_an_obligation
    assert not by_number["2.1"].states_an_obligation


def test_a_conduct_section_still_states_an_obligation(parsed):
    """The test is vocabulary versus duty, **not** conduct versus control.
    § 2.13 is conduct and is not crosswalkable, but it plainly states
    duties, and a parser that dropped it here would be pre-empting the
    open shape question instead of answering this one."""
    conduct = next(s for s in parsed if s.number == "2.13")

    assert conduct.states_an_obligation


def test_a_control_section_with_a_conduct_heading_is_not_dropped(parsed):
    """§ 2.19 reads administrative and its body is media sanitization.
    Nothing here may classify on the heading alone."""
    disposition = next(s for s in parsed if s.number == "2.19")

    assert disposition.states_an_obligation
    assert "sanitizing any associated hard copy or electronic media" in disposition.text


def test_a_reserved_section_states_no_obligation():
    """Not in Part 2 today, which is why it is constructed rather than
    drawn from the fixture: a `[Reserved]` section is countable, plausible
    and empty, and every check except "is this real" passes on it."""
    reserved = Section(number="2.99", title="[Reserved]", text="")

    assert not reserved.states_an_obligation
