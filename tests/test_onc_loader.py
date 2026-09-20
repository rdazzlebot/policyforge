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


@pytest.fixture(scope="module")
def fixture_xml() -> str:
    """The same excerpt the `paragraphs` fixture is built from, unparsed,
    because the emitter takes XML rather than paragraphs."""
    return FIXTURE.read_text(encoding="utf-8")


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


# --------------------------------------------------------------------------
# The emitter, run rather than read
# --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def emitted(fixture_xml):
    from policyforge.ingest.onc_loader import parse_onc_criteria

    return parse_onc_criteria(fixture_xml)


def test_a_criterion_keeps_the_half_of_its_title_that_distinguishes_it(emitted):
    """`(a)(1)`, `(a)(2)` and `(a)(3)` are all "Computerized provider order
    entry" and differ only after the em dash. A title cut at the dash gives
    them one name between them -- which reads as a duplicate rather than as
    a parse fault, so nothing looks broken.
    """
    controls, _reserved = emitted
    cpoe = next(c for c in controls if c.control_id == "170.315(a)(1)")

    assert cpoe.title == "Computerized provider order entry—medications"
    assert "—" in cpoe.title, "the distinguishing half is after the dash"


def test_a_reserved_criterion_is_found_and_not_emitted(emitted):
    """The pairing `is_reserved`'s docstring describes: the source-side
    test proves the parser *saw* ten letters, and this proves it emitted
    nine deliberately. Either alone is half an argument."""
    controls, reserved = emitted

    assert "170.315(i)" in reserved
    assert not any(c.control_id.startswith("170.315(i)") for c in controls)


def test_the_emitted_and_reserved_sets_do_not_overlap(emitted):
    """A criterion cannot be both. If it were, the reported count of
    exclusions would be describing entries that also shipped."""
    controls, reserved = emitted

    assert not ({c.control_id for c in controls} & set(reserved))


def test_a_reserved_range_advances_the_counter_to_its_end(emitted):
    """`(1)-(19) [Reserved]` is one paragraph standing for nineteen
    criteria. Advancing by one instead would leave the next real criterion
    -- `(j)(20)` -- failing the successor rule and silently dropped, taking
    the rest of its category with it.
    """
    from policyforge.ingest.onc_loader import _CRITERION_NUMBER

    match = _CRITERION_NUMBER.match("(1)-(19) [Reserved]")

    assert match is not None
    assert match.group("first") == "1"
    assert match.group("last") == "19", "the range's end is what the counter must move to"


def test_a_category_introduced_with_a_period_is_not_lost(emitted):
    """`(a) Clinical—` puts its first criterion after an em dash;
    `(j) Modular API capabilities.` uses a period and its criteria follow
    in later paragraphs. Matching only the dash loses category (j) whole,
    and the catalog simply has one fewer category with nothing to say so.
    """
    from policyforge.ingest.onc_loader import _CATEGORY_NAME

    dashed = _CATEGORY_NAME.match("(a) Clinical—(1) Computerized provider order entry")
    stopped = _CATEGORY_NAME.match("(j) Modular API capabilities. The following outcomes")

    assert dashed and dashed.group("name") == "Clinical"
    assert stopped and stopped.group("name") == "Modular API capabilities"


def test_every_emitted_criterion_carries_its_statement(emitted):
    """No exception for reserved paragraphs: an exception has to be kept
    in step with the source and can drift, a rule with none cannot."""
    controls, _reserved = emitted

    for control in controls:
        assert control.control_statement.strip(), control.control_id
        assert control.title.strip(), control.control_id


def test_the_parse_refuses_a_document_with_no_criteria():
    """An empty parse is the failure that passes every check downstream,
    so it raises rather than returning nothing."""
    import pytest as _pytest

    from policyforge.ingest.onc_loader import parse_onc_criteria

    with _pytest.raises(ValueError, match="parser fault"):
        parse_onc_criteria("<DIV5><DIV8 N='170.999'><P>Nothing here.</P></DIV8></DIV5>")


def test_a_reserved_range_yields_every_id_it_stands_for(emitted):
    """`(6)-(8) [Reserved]` is one paragraph standing for three criteria.
    Reporting it as one would undercount what was excluded, and the run
    would look broken to anyone checking 1..9 against the source."""
    _controls, reserved = emitted

    assert {"170.315(a)(6)", "170.315(a)(7)", "170.315(a)(8)"} <= set(reserved)


def test_the_criterion_after_a_reserved_range_is_still_emitted(emitted):
    """The counter has to advance to the range's END. Advancing by one
    leaves `(9)` failing the successor rule, so it is dropped -- and every
    later criterion in that category with it, silently."""
    controls, _reserved = emitted
    letters_a = [c.control_id for c in controls if c.family_abbr == "(a)"]

    assert "170.315(a)(9)" in letters_a, "the criterion after the range was lost"
    assert letters_a == [
        "170.315(a)(1)",
        "170.315(a)(2)",
        "170.315(a)(3)",
        "170.315(a)(4)",
        "170.315(a)(5)",
        "170.315(a)(9)",
    ]


def test_sub_list_paragraphs_are_not_read_as_criteria(emitted):
    """The fixture carries four real decoys: `(1) To a specific set of
    identified users.` and `(2) As a system administrative function.` are
    three levels inside `(a)(4)`, and two more sit inside `(a)(5)`.

    A rule that reads any `(N)` as a criterion emits six extra controls
    from this one category, each with an id naming a sub-clause. Nothing
    raises; the catalog simply gains entries an assessor cannot follow.
    """
    controls, _reserved = emitted
    ids = {c.control_id for c in controls}

    # (a)(1) and (a)(2) are real; a second reading of the decoys would
    # produce duplicates or push the run past (9).
    assert len([c for c in controls if c.family_abbr == "(a)"]) == 6
    assert "170.315(a)(10)" not in ids
