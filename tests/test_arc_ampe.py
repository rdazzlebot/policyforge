"""ARC-AMPE Volume II, and finding the catalog inside an SSPP template.

The workbooks built here are invented, but their awkward shape is copied
from CMS's: a controls sheet that opens with a title, an instruction
paragraph and a twenty-row family index before its header; a separate
`Instructional Guidance` sheet that reproduces that same header over a
three-row worked example; six pairs of blank implementation columns to the
right of the data; and a guidance cell that says, in words, that there is no
guidance.

That last pair is the point of most of these tests. Captions alone pick the
wrong sheet — the decoy matches every one of them, and matches earlier in
the workbook — which is a failure that produces a plausible three-control
catalog rather than an error.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from policyforge.ingest import arc_ampe
from policyforge.ingest.schema import load_controls

CATALOG = Path("data/frameworks/arc-ampe/controls.json")

HEADER = [
    "#",
    "Control Family",
    "Control Number",
    "Control Name",
    "ARC-AMPE CONTROL",
    "ARC-AMPE SUPPLEMENTAL CONTROL REQUIREMENTS & GUIDANCE",
    "Related Controls",
    "MASTER / OVERALL Control Status",
    "Control Implementation Description",
]

NO_GUIDANCE = "•  There are no supplemental control requirements and guidance for this control."


def _sheet(workbook, title: str, rows: list[list[object]], *, preamble: int = 0):
    sheet = workbook.create_sheet(title)
    for _ in range(preamble):
        sheet.append(["Access Control (AC)"])
    sheet.append(HEADER)
    for row in rows:
        sheet.append(row)
    return sheet


def _row(number: int, cid: str, name: str, statement: str, guidance: str, related: str):
    return [number, "Access Control", cid, name, statement, guidance, related, None, None]


@pytest.fixture
def workbook():
    """A template shaped like CMS's: a decoy sheet first, the catalog second."""
    from openpyxl import Workbook

    book = Workbook()
    book.remove(book.active)

    # The decoy. Same header, three rows, and it comes first in the book.
    _sheet(
        book,
        "Instructional Guidance",
        [_row(1, "AC-01", "Example", "Example statement.", NO_GUIDANCE, "None.")],
    )
    _sheet(
        book,
        "AE Mandatory Baseline",
        [
            _row(1, "AC-01", "Policy", "a. Develop.", "•  Define roles.", "IA-1, PM-9"),
            _row(2, "AC-02", "Account Management", "a. Define.", NO_GUIDANCE, "None."),
            _row(3, "AC-02(01)", "Automated Management", "Support.", "•  Use automation.", "AC-2"),
            _row(4, "AC-03(08)", "Revocation", "Enforce.", NO_GUIDANCE, ""),
            # A section band: real text, no control number. Worth reporting.
            [None, "Awareness and Training", None, None, None, None, None, None, None],
            # Padding. Not worth reporting.
            [None, None, None, None, None, None, None, None, None],
        ],
        preamble=20,
    )
    return book


# --------------------------------------------------------------------------
# Finding the sheet
# --------------------------------------------------------------------------


def test_the_catalog_wins_over_a_decoy_with_the_same_header(workbook):
    """`Instructional Guidance` matches every caption the real sheet does.

    It also appears first, so a caption-scored search picks it and returns a
    three-control catalog that looks entirely reasonable. Rows carrying a
    control number are what separate a catalog from an illustration of one.
    """
    title, columns, data_start = arc_ampe.find_controls_sheet(workbook)

    assert title == "AE Mandatory Baseline"
    assert columns["control_id"] == 2
    assert data_start == 22, "header sits below the twenty-row family index"


def test_a_workbook_with_no_controls_sheet_says_which_captions_it_wanted():
    from openpyxl import Workbook

    book = Workbook()
    book.active.append(["Version", "Date", "Author"])

    with pytest.raises(ValueError, match="Control Number"):
        arc_ampe.find_controls_sheet(book)


def test_the_error_names_volume_i_as_the_likely_mistake():
    """The obvious source is the wrong one, so the error says so.

    Volume I is the narrative PDF and holds no controls; somebody who
    downloaded it and got an unhelpful parse error would have no way to
    learn that from the failure.
    """
    from openpyxl import Workbook

    book = Workbook()
    with pytest.raises(ValueError, match="Volume I"):
        arc_ampe.find_controls_sheet(book)


# --------------------------------------------------------------------------
# Rows
# --------------------------------------------------------------------------


def test_enhancements_attach_to_the_control_they_enhance(workbook):
    controls, summary = arc_ampe.parse_arc_ampe(workbook)
    by_id = {c.control_id: c for c in controls}

    assert [c.control_id for c in controls] == ["AC-1", "AC-2", "AC-3"]
    assert [e.enhancement_id for e in by_id["AC-2"].enhancements] == ["AC-2(1)"]
    assert summary.controls == 2
    assert summary.enhancements == 2


def test_a_control_stated_only_as_an_enhancement_still_gets_a_parent(workbook):
    """The baseline includes AC-3(8) without AC-3.

    `Control.enhancements` is the only container the schema has, so the
    parent exists and carries no statement — which is the truth about it.
    """
    controls, _ = arc_ampe.parse_arc_ampe(workbook)
    parent = {c.control_id: c for c in controls}["AC-3"]

    assert parent.control_statement == ""
    assert [e.enhancement_id for e in parent.enhancements] == ["AC-3(8)"]


def test_the_template_saying_there_is_no_guidance_becomes_no_guidance(workbook):
    """That sentence is the template speaking, not CMS.

    Carried through, it reaches a generated document as if it were
    supplemental guidance CMS wrote.
    """
    controls, summary = arc_ampe.parse_arc_ampe(workbook)
    by_id = {c.control_id: c for c in controls}

    assert by_id["AC-2"].discussion == ""
    assert by_id["AC-1"].discussion == "•  Define roles."
    assert summary.with_guidance == 2


@pytest.mark.parametrize(
    "wording",
    [
        "•  There are no supplemental control requirements and guidance for this control.",
        "•  There are no supplemental control requirements & guidance at this time.",
        "•  There are no supplemental control requireandents and guidance at this time.",
        "There is no supplemental control requirement and guidance.",
        "THERE ARE NO SUPPLEMENTAL CONTROL REQUIREMENTS & GUIDANCE.",
    ],
    ids=["and", "ampersand", "corrupted-word", "singular", "shouting"],
)
def test_every_spelling_of_the_boilerplate_becomes_no_guidance(wording: str):
    """**v1.02 shipped nineteen fields that this used to miss.**

    The sentence is retyped per row and drifts. Eighteen write "&" where
    the pattern wanted "and"; `PE-2` reads "requireandents", a
    find-and-replace of "&" that ran through the middle of the word. Each
    one was kept and rendered into documents as if CMS had written it.

    `corrupted-word` is not hypothetical tidiness — it is the exact
    string in the published workbook.
    """
    assert arc_ampe._guidance(wording) == ""


def test_guidance_that_merely_mentions_the_phrase_survives():
    """**The opposite error, which searching the cell invites.**

    A row whose guidance genuinely discusses supplemental control
    requirements must not be discarded because the sentinel appears
    inside it. The rule is that every sentence is boilerplate, so one
    real sentence beside it keeps the whole cell.
    """
    cell = (
        "Agencies must document supplemental control requirements and guidance "
        "annually. There are no supplemental control requirements and guidance "
        "for sub-part (b)."
    )

    assert arc_ampe._guidance(cell) == cell


def test_bullets_and_curly_quotes_survive_but_editing_artifacts_do_not():
    """CMS structures normative prose with bullets; Excel leaves NBSPs."""
    assert arc_ampe._clean("•  Text\xa0here  \n\n") == "•  Text here"


@pytest.mark.parametrize(
    ("cell", "expected"),
    [
        ("IA-1, PM-9, PS-8, SI-12 ", ["IA-1", "PM-9", "PS-8", "SI-12"]),
        ("None.", []),
        ("", []),
        ("AC-02(01); AC-17", ["AC-2(1)", "AC-17"]),
        ("AC-2, AC-2", ["AC-2"]),
    ],
)
def test_related_controls_are_matched_not_split(cell, expected):
    """Splitting on separators yields a related control called "None".

    The cell is free text and says "None." as often as it lists anything, so
    tokens are matched instead — which also normalizes `AC-02(01)` on the way
    through, since these become citations.
    """
    assert arc_ampe.split_related(cell) == expected


def test_only_rows_with_content_count_as_skipped(workbook):
    """A padded blank is not a dropped row, and reporting it as one buries
    the case that matters: real text whose control number went missing."""
    _, summary = arc_ampe.parse_arc_ampe(workbook)
    assert summary.rows_skipped == 1


def test_scanning_for_the_header_does_not_extend_the_sheet(workbook):
    """openpyxl materializes rows read past a writable sheet's last one.

    Left unbounded, detection itself pushes `max_row` out to the scan depth
    and every later read walks rows this loader invented.
    """
    before = workbook["AE Mandatory Baseline"].max_row
    arc_ampe.find_controls_sheet(workbook)

    assert workbook["AE Mandatory Baseline"].max_row == before


# --------------------------------------------------------------------------
# The crosswalk
# --------------------------------------------------------------------------


def test_controls_are_anchored_only_on_ids_the_catalog_actually_defines(workbook):
    controls, summary = arc_ampe.parse_arc_ampe(workbook, nist_ids={"AC-1", "AC-2", "AC-2(1)"})
    by_id = {c.control_id: c for c in controls}

    assert by_id["AC-1"].source_crosswalk == {arc_ampe.NIST_SOURCE: "AC-1"}
    assert by_id["AC-3"].enhancements[0].source_crosswalk == {}
    assert summary.crosswalked == 3
    assert summary.unresolved == ["AC-3(8)"]


def test_without_a_catalog_nothing_is_crosswalked(workbook):
    """Usable on its own, just invisible to `policyforge map`."""
    controls, summary = arc_ampe.parse_arc_ampe(workbook)

    assert all(not c.source_crosswalk for c in controls)
    assert summary.crosswalked == 0
    assert summary.unresolved == []


# --------------------------------------------------------------------------
# The committed catalog
# --------------------------------------------------------------------------


@pytest.mark.skipif(not CATALOG.exists(), reason="ARC-AMPE catalog not built")
def test_the_committed_catalog_holds_the_baseline_cms_published():
    """402 is CMS's own published figure for an ACA Administering Entity.

    A count that drifts means the sheet moved, the header changed, or the
    decoy won — all of which produce a catalog that still parses.
    """
    controls = load_controls(CATALOG)
    items = len(controls) + sum(len(c.enhancements) for c in controls)

    assert items == 402
    assert all(c.baseline == arc_ampe.AE_BASELINE for c in controls)


def test_no_shipped_field_says_there_is_no_guidance():
    """**The artefact half, which the parser tests cannot cover.**

    `_guidance` running correctly says nothing about what was committed:
    `controls.json` is a static file, and a parser fixed after the
    catalog was generated leaves the boilerplate sitting in it. Nineteen
    fields shipped that way — nine control `discussion`s and ten
    enhancement `additional_requirements`.

    Stated over **every text field of every entry**, not over the one
    field the defect was found in. I found nine by looking at
    `discussion`; the fix found nineteen because it operates on the
    function rather than on the field I happened to check.
    """
    controls = load_controls(CATALOG)
    texts = [
        (c.control_id, field, getattr(c, field))
        for c in controls
        for field in ("control_statement", "discussion", "additional_requirements")
    ] + [
        (e.enhancement_id, field, getattr(e, field))
        for c in controls
        for e in c.enhancements
        for field in ("description", "additional_requirements")
    ]
    # Asked through the production decision rather than a copy of it, so the
    # guard cannot drift from the rule it is guarding — and so it asks the
    # same question: is this field *only* the boilerplate?
    boilerplate = [
        (ident, field) for ident, field, text in texts if text and arc_ampe._guidance(text) == ""
    ]

    assert boilerplate == []
