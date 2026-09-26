"""Block structure read from markdown-it (#376), and list numbers (#365).

The rebuild is held to conservation over the saved generated corpus (on the
issue); these pin the shapes that measurement found, and #365's three.
Expected answers come from today's behaviour or from markdown-it, never from
the code under test.
"""

from __future__ import annotations

from markdown_it import MarkdownIt

from policyforge.content.deontic import _line_kinds, analyze

AC2 = "[NIST 800-53 AC-2]"
CP2 = "*[NIST CP-2(7)]*"


def _texts(text: str) -> list[str]:
    return [s.text for s in analyze(text)]


# ---- #365: a list number is not a sentence -----------------------------------


def test_a_list_number_the_splitter_cut_off_is_not_a_statement():
    """`1. Open ...` read as `1.` and `Open ...`: 4,133 of the 45 Procedures'
    statements were such numbers."""
    text = "1. Open the console.\n1. Close the console.\n"
    assert _texts(text) == ["Open the console.", "Close the console."]
    # `1)` never was: the splitter breaks only at `.`, `!` or `?`, so the
    # number stays in its sentence, as it did before #365.
    assert _texts(text.replace("1.", "1)")) == ["1) Open the console.", "1) Close the console."]


def test_a_number_under_a_sentence_is_not_glued_to_its_end():
    """Inside a colon list the number used to end the item above
    (`... broadcasting. 1.`)."""
    text = "Configure each of the following:\n1. Disable broadcasting.\n1. Enable encryption.\n"
    assert not any(t.endswith(" 1.") or t == "1." for t in _texts(text))
    assert _texts(text)[-1] == "Enable encryption."


def test_a_number_the_splitter_never_cut_off_keeps_its_text():
    """Conservation: `1. item two` and `1. **Scope.**` were one piece before
    #365 and still are."""
    assert _texts("1. item two shall log.") == ["1. item two shall log."]
    assert _texts("1. **Scope.** The owner must act.")[0].startswith("1. **Scope.**")


def test_line_numbers_and_citations_stay_on_their_sentence():
    text = f"Intro.\n\n1. Open the console {AC2}.\n1. Close the console.\n"
    statements = analyze(text)
    assert [(s.line, s.text, s.citations) for s in statements] == [
        (1, "Intro.", ()),
        (3, f"Open the console {AC2}.", (AC2,)),
        (4, "Close the console.", ()),
    ]


def test_a_numbered_colon_list_reads_like_a_bulleted_one():
    """#351/#354: the lead-in and its items are one statement for citation
    crediting. A bulleted list already read so; the number split a numbered
    one. The citation reaches the lead-in's obligation both ways."""
    for marker in ("- ", "1. "):
        text = f"The owner must:\n{marker}keep a register;\n{marker}Review it quarterly {AC2}.\n"
        first = analyze(text)[0]
        assert first.binds and first.citations == (AC2,), (marker, first)


# ---- citation-only lines the measurement found -------------------------------


def test_a_citation_under_a_heading_with_a_list_below_stays_its_own():
    """Measured on a generated Procedure: the section's scoping citation, a
    blank line, then the steps. It was a statement of its own before #376,
    and the first step does not borrow it."""
    text = f"### Coordinate\n\n{CP2}\n\n1. Site Reliability Engineering coordinates the plan.\n"
    statements = analyze(text)
    assert statements[0].text == CP2 and statements[0].cited
    assert statements[1].text == "Site Reliability Engineering coordinates the plan."
    assert statements[1].citations == ()


def test_a_citation_alone_in_its_section_does_not_cross_the_heading():
    """With no sentence of its own section to credit, it credits nothing, as
    before #376, and never the next section's sentence (#349)."""
    text = f"### One\n\n{AC2}\n\n### Two\n\nThe owner must act.\n"
    (statement,) = analyze(text)
    assert statement.text == "The owner must act." and statement.citations == ()


def test_a_citation_under_a_heading_opens_the_paragraph_below():
    """With a paragraph (not a list) below, the citation goes to it, as before."""
    text = f"### One\n\n{AC2}\n\nThe owner must act.\n"
    (statement,) = analyze(text)
    assert statement.citations == (AC2,) and statement.binds


def test_a_citation_indented_under_a_colon_list_is_the_whole_lists():
    """Inside the last item by CommonMark's indentation, after a blank line:
    still the list's own, shared by every item (#354), as at 74779c4. A
    mutation giving it to the last item alone survived every other test."""
    from policyforge.content.deontic import _colon_units

    text = f"Acme Health must:\n\n- maintain a register;\n- review access quarterly.\n\n  {AC2}\n"
    units, _ = _colon_units(text, analyze(text))
    assert [(u.line, u.citations) for u in units] == [(3, (AC2,)), (4, (AC2,))]


# ---- the structure is markdown-it's ------------------------------------------


def test_headings_are_markdown_its_except_the_lone_dash():
    """Every heading line markdown-it reports is a heading line here, and
    nothing else is, except the lone `-` underline kept by choice (1d on
    #350). Inputs from shapes the regexes each missed once."""
    text = (
        "# A\nText\n===\n> ## Quoted\n##\nPara\n-\n\n***\n- - -\nPlain\n---\n"
        "- item\n---\n1. one\n\n    indented code\n"
    )
    lines = text.split("\n")
    expected = set()
    for token in MarkdownIt("commonmark").parse(text):
        if token.type == "heading_open" and not (
            token.markup == "-" and lines[token.map[1] - 1].strip() == "-"
        ):
            expected.update(range(*token.map))
        if token.type == "hr":
            expected.add(token.map[0])
    got = {i for i, kind in enumerate(_line_kinds(lines)) if kind}
    assert got == expected
    assert 6 not in got, "the lone `-` under 'Para' is not an underline"
