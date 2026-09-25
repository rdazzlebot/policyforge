"""A heading ends a sentence, and nothing is credited across one (#349).

`analyze` blanked headings and read straight through them. Measured over 33
generated Standards, 18 of 2,501 statements ran across a heading. One was
glm's `... [Playbook Map 1.6 Action 8].` running into the next section's
`- **CAT-01:** ... shall ensure ... [NIST AI RMF Map 2]`, so a check read
CAT-01's obligation and Core citation as NIST's suggestion. One test per
heading shape (1d's conditions), and the two joins that must survive.
"""

from __future__ import annotations

import pytest

from policyforge.content.deontic import analyze

TAG_A = "[NIST 800-53 AC-2]"
TAG_B = "[NIST 800-53 AU-6]"


def _by_start(text: str) -> dict[str, tuple[int, tuple[str, ...]]]:
    """Each statement's first word -> (line, citations)."""
    return {s.text.split()[0]: (s.line, s.citations) for s in analyze(text)}


@pytest.mark.parametrize(
    "heading",
    [
        "## Next section",
        "### 3.1 Requirements",
        "Next section\n============",
        "Next section\n------------",
    ],
    ids=["atx-h2", "atx-h3", "setext-equals", "setext-dashes"],
)
def test_a_sentence_does_not_run_across_a_heading(heading):
    """The glm shape: a sentence ending in its own tag and full stop, a
    heading, then a bullet whose tag is its own."""
    text = (
        f"Alpha keeps a register {TAG_A}.\n\n{heading}\n\n"
        f"- **B-01:** Bravo shall review logs. {TAG_B}\n"
    )

    statements = analyze(text)

    alpha = next(s for s in statements if s.text.startswith("Alpha"))
    assert alpha.citations == (TAG_A,), "Bravo's tag was credited across the heading"
    assert "shall" not in alpha.text
    assert any("Bravo shall review logs" in s.text and TAG_B in s.citations for s in statements)
    assert not any("Next section" in s.text for s in statements), "heading text is not a sentence"


@pytest.mark.parametrize(
    "boundary",
    [
        "***",
        "___",
        "- - -",
        "* * *",
        "Next section\n=",
        "Next section\n==",
        "Next section\n--",
        "> ## Quoted heading",
        "##",
    ],
    ids=["break-stars", "break-underscores", "break-spaced-dashes", "break-spaced-stars",
         "setext-one-equals", "setext-two-equals", "setext-two-dashes", "quoted-atx", "bare-atx"],
)  # fmt: skip
def test_the_colon_lead_in_does_not_take_the_next_sections_citation(boundary):
    """1d's shapes on #350, none of which the 33-Standard corpus contains:
    the lead-in "must identify:" took the next section's citation across
    each of them."""
    text = f"Alpha must identify:\n\n{boundary}\n\nBravo shall review logs. {TAG_B}\n"

    statements = analyze(text)

    alpha = next(s for s in statements if s.text.startswith("Alpha"))
    assert alpha.citations == (), f"the citation crossed {boundary!r}"
    assert "Bravo" not in alpha.text
    assert [s.citations for s in statements if s.text.startswith("Bravo")] == [(TAG_B,)]


def test_a_paragraph_above_a_thematic_break_stays_text():
    """`***` is never a setext underline, so the line above it is not a heading."""
    texts = [s.text for s in analyze("Charlie must act.\n***\nDelta must act.\n")]
    assert texts == ["Charlie must act.", "Delta must act."]


def test_two_dashes_with_no_paragraph_above_are_neither_heading_nor_break():
    """`--` is a setext underline only under a paragraph line; alone, it is
    text: nothing is blanked and the text stays one block. Asked of the block
    split directly, because the sentence splitter then joins `act. --` on its
    own rule (no capital after the full stop), which is not this question."""
    from policyforge.content.deontic import _heading_blocks

    text = "Echo must act.\n\n--\n"
    blanked, blocks = _heading_blocks(text)
    assert blanked == text
    assert blocks == [(0, text)]


def test_a_heading_right_after_a_list_item_ends_it():
    text = f"- Charlie reviews access\n## Section\nDelta must log changes. {TAG_B}\n"

    statements = analyze(text)

    charlie = [s for s in statements if "Charlie" in s.text]
    assert len(charlie) == 1
    assert "Delta" not in charlie[0].text and charlie[0].citations == ()
    assert [(s.line, s.citations) for s in statements if s.text.startswith("Delta")] == [
        (3, (TAG_B,))
    ]


def test_a_heading_right_after_a_table_row_ends_it():
    text = f"| Echo | monthly |\n### Section\nFoxtrot must rotate keys. {TAG_B}\n"

    statements = analyze(text)

    assert [s.citations for s in statements if "Echo" in s.text] == [()]
    assert [s.line for s in statements if s.text.startswith("Foxtrot")] == [3]


def test_a_rule_under_a_list_item_is_a_break_not_a_heading():
    """`---` under a list item is a thematic break: it ends the block, but
    the list item above it is still text, not heading text to blank."""
    text = "- Golf must be kept\n---\nHotel follows.\n"

    texts = [s.text for s in analyze(text)]

    assert any("Golf must be kept" in t for t in texts)
    assert not any("Golf" in t and "Hotel" in t for t in texts)


def test_a_sentence_wrapped_across_two_ordinary_lines_still_joins():
    text = f"India must review every account\nat least quarterly. {TAG_A}\n"

    (statement,) = analyze(text)

    assert statement.text == "India must review every account at least quarterly."
    assert statement.citations == (TAG_A,)
    assert statement.line == 1


def test_a_citation_on_the_line_below_still_attaches_to_its_sentence():
    """The shape `analyze`'s docstring was written for, inside one block."""
    text = f"## Access\n\nJuliet must disable stale accounts.\n{TAG_A}\n\nKilo is next.\n"

    starts = _by_start(text)

    assert starts["Juliet"] == (3, (TAG_A,))
    assert starts["Kilo"][1] == ()


def test_a_citation_opening_a_block_stays_with_the_sentence_it_opens():
    """Nothing above it in the block: it must not cross the heading back."""
    text = f"Lima is done.\n\n## Next\n\n{TAG_A} Mike must act.\n"

    starts = _by_start(text)

    assert starts["Lima"][1] == ()
    assert starts["Mike"][1] == (TAG_A,)


def test_line_numbers_still_point_at_the_document():
    text = "# Title\n\nNovember must act.\n\nSubtitle\n--------\n\nOscar must act.\n"

    starts = _by_start(text)

    assert starts["November"][0] == 3
    assert starts["Oscar"][0] == 8
