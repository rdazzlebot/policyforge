"""GovRAMP's structure, and reading it out of the workbook it arrives in.

Every fixture here is invented. The *shape* is modelled on a published
GovRAMP controls matrix -- the fourteen-sheet SSP template, the two-row
header with merged group titles above the captions, the Core/Ready/
Authorized columns, the totals row below the data and the blank tail below
that -- but the control text, the parameter values and the added
requirements are made up. That is deliberate rather than merely cautious:
GovRAMP's Terms & Conditions claim ownership of their published documents,
this repository is public, and a fixture is a file that gets committed.

The 800-53 identifiers (`AC-1`, `AC-2 (1)`) are NIST's and public domain,
and they have to be real ones: the whole point of the crosswalk is that a
profile's identifiers join to the catalog it profiles, and a fixture with
invented identifiers would test the join against nothing.

Building the workbook here rather than committing one also makes the tests
better. A fixture written to exercise the awkward cases -- a continuation
line with no citation, a tier column deliberately misaligned, an
enhancement whose base control is absent -- exercises them every run, which
a copy of a real matrix would only do by luck.
"""

from __future__ import annotations

import pytest
from openpyxl import Workbook

from policyforge.ingest import govramp
from policyforge.ingest import govramp_export as export
from policyforge.ingest.govramp import AUTHORIZED, CORE, READY

# --------------------------------------------------------------------------
# A synthetic workbook
# --------------------------------------------------------------------------

#: Row 1 of the controls sheet: group titles spanning merged cells. openpyxl
#: reports a merged span as its value in the first cell and `None` in the
#: rest, which is exactly what a list with blanks reproduces.
GROUP_ROW = [
    "Control Information\n",
    None,
    None,
    None,
    None,
    None,
    None,
    None,
    "GovRAMP Parameters",
    None,
]

#: Row 2: the captions that actually name the columns. The parentheticals
#: are the kind the real workbook carries -- a NIST publication date that
#: will change -- and are here so the substring matching is under test
#: rather than an exact-caption match that happens to pass.
CAPTION_ROW = [
    "Count\n",
    "Required for Core",
    "Required for Ready",
    "Required for Authorized",
    "SORT ID\n",
    "Family",
    "ID",
    "Control Name",
    "NIST Control Description\n (From NIST SP 800-53r5 12/10/2020)",
    "NIST Discussion\n (From NIST SP 800-53r5 12/10/2020)",
    "GovRAMP-Defined Assignment / Selection Parameters \n (Numbering matches SSP)",
    "Additional GovRAMP Requirements and Guidance",
]


def _row(
    count,
    core,
    ready,
    authorized,
    sort_id,
    family,
    control_id,
    name,
    statement,
    discussion="",
    parameters="",
    additional="",
):
    return [
        count,
        core,
        ready,
        authorized,
        sort_id,
        family,
        control_id,
        name,
        statement,
        discussion,
        parameters,
        additional,
    ]


#: Invented control text throughout. The shape of each row is real; the
#: words are not.
DATA_ROWS = [
    _row(
        1,
        "No",
        "No",
        "Yes",
        "AC-01",
        "ACCESS CONTROL",
        "AC-1",
        "Policy and Procedures",
        "a. Publish an access policy to [Assignment: organization-defined roles];",
        "A policy says who decides.",
        "AC-1 (c) (1) [every other harvest] \nAC-1 (c) (2) [each full moon] [after any flood]",
    ),
    _row(
        2,
        "Yes",
        "Yes",
        "Yes",
        "AC-02",
        "ACCESS CONTROL",
        "AC-2",
        "Account Management",
        "a. Keep a register of accounts and the people who hold them;",
        "Accounts outlive the people who asked for them.",
        "AC-2 (j) [twice per lunar cycle]",
    ),
    _row(
        3,
        "Yes",
        "Yes",
        "Yes",
        "AC-02 (01)",
        "ACCESS CONTROL",
        "AC-2 (1)",
        "Account Management\nAutomated Register Upkeep",
        "Keep the register using [Assignment: organization-defined machinery].",
    ),
    # The continuation case: a second line with no citation of its own, which
    # belongs to the citation above it.
    _row(
        4,
        "No",
        "No",
        "Yes",
        "AC-02 (02)",
        "ACCESS CONTROL",
        "AC-2 (2)",
        "Account Management\nTemporary Accounts",
        "Automatically [Selection: retire; suspend] temporary accounts.",
        "",
        "AC-2 (2) [Selection: suspends] \n[Assignment: no more than two market days]",
    ),
    # No space before the bracket, and a trailing note outside it.
    _row(
        5,
        "No",
        "No",
        "Yes",
        "AC-02 (03)",
        "ACCESS CONTROL",
        "AC-2 (3)",
        "Account Management\nDormant Accounts",
        "Close accounts after [Assignment: organization-defined idleness].",
        "",
        "AC-2 (3) (d)[ninety (90) sunrises] (See additional requirements and guidance.)",
        "AC-2 (3) Requirement: The provider states the idleness period for\n"
        "accounts held by machinery rather than people.",
    ),
    # The family whose heading carries a trailing word that is not part of
    # its name.
    _row(
        6,
        "No",
        "Yes",
        "Yes",
        "SR-11",
        "SUPPLY CHAIN RISK MANAGEMENT FAMILY",
        "SR-11",
        "Component Authenticity",
        "Guard against counterfeit components.",
    ),
]

#: What sits below the controls in the real workbook: a totals row with no
#: identifier, then blanks. Neither is a control.
TRAILING_ROWS = [
    [None, None, 80, 319, None, None, None, None, None, None, None, None],
    [None] * 12,
    [None] * 12,
]


def build_workbook(
    path,
    *,
    data_rows=None,
    caption_row=None,
    cover=("GovRAMP Rev. 5", "Moderate Baseline"),
    instructions=("Controls Matrix for a Moderate Impact System",),
    controls_sheet_name="12_Mod Controls",
):
    """Write a workbook shaped like a GovRAMP matrix.

    Decoy sheets are included on purpose. The controls sheet is found by its
    captions rather than its name, and a workbook with only one sheet would
    let a loader that simply took `book.active` pass.

    `cover` and `instructions` are separately blankable because the real
    workbook states its impact level in both places, and a test of the
    filename fallback has to silence both to reach it.
    """
    book = Workbook()

    cover_sheet = book.active
    cover_sheet.title = "Cover Sheet"
    for line in cover:
        cover_sheet.append([line])

    instructions_sheet = book.create_sheet("Instructions")
    for line in instructions:
        instructions_sheet.append([None, None, line])
    instructions_sheet.append([None, "Template Version History"])

    inventory = book.create_sheet("11_Inventory Workbook")
    inventory.append(["UNIQUE ASSET IDENTIFIER", "IPv4 or IPv6 Address", "Virtual"])
    inventory.append(["asset-1", "10.0.0.1", "Yes"])

    sheet = book.create_sheet(controls_sheet_name)
    sheet.append(GROUP_ROW)
    sheet.append(caption_row if caption_row is not None else CAPTION_ROW)
    for row in data_rows if data_rows is not None else DATA_ROWS:
        sheet.append(row)
    for row in TRAILING_ROWS:
        sheet.append(row)

    book.save(path)
    return path


@pytest.fixture
def matrix(tmp_path):
    return build_workbook(tmp_path / "GovRAMP-Controls-Matrix_Mod_Rev5_V1.06.xlsx")


# --------------------------------------------------------------------------
# Identifiers
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("AC-1", ("AC-1", "")),
        ("AC-2 (1)", ("AC-2", "AC-2(1)")),
        # The SORT ID spelling of the same control, zero-padded in both
        # halves. It has to resolve to the same identifier as the line above
        # or one workbook yields two spellings of one control.
        ("AC-02 (01)", ("AC-2", "AC-2(1)")),
        ("AC-2(1)", ("AC-2", "AC-2(1)")),
        ("  sr-11  ", ("SR-11", "")),
        ("AC-2 (13)", ("AC-2", "AC-2(13)")),
    ],
)
def test_a_control_id_normalizes_to_the_spelling_the_catalog_uses(value, expected):
    assert govramp.parse_control_id(value) == expected


def test_an_unrecognisable_identifier_is_kept_rather_than_dropped():
    """A row that reached the parser is a row of the matrix. A control
    missing from a scope report is worse than one with an odd id -- and
    `summarize` reports these, so it is visible either way."""
    assert govramp.parse_control_id("AC-2 through AC-5") == ("AC-2 through AC-5", "")


def test_enhancement_ids_match_the_oscal_loaders_spelling():
    """`AC-2(1)`, no space. This is the crosswalk's join key: the profile and
    the catalog it profiles share identifiers, and `AC-2 (1)` joins to
    nothing."""
    _, enhancement = govramp.parse_control_id("AC-02 (01)")
    assert enhancement == "AC-2(1)"
    assert govramp.family_abbr(enhancement) == "AC"


# --------------------------------------------------------------------------
# Families and titles
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("ACCESS CONTROL", "Access Control"),
        # "and" stays lowercase, matching the OSCAL catalog's spelling. Both
        # end up in one merged catalog, so they have to agree.
        ("SYSTEM AND COMMUNICATIONS PROTECTION", "System and Communications Protection"),
        # The trailing word is an artifact of the heading, and left in it
        # matches no other catalog's name for this family.
        ("SUPPLY CHAIN RISK MANAGEMENT FAMILY", "Supply Chain Risk Management"),
        # Already mixed case: written deliberately, so left alone.
        ("Media Protection", "Media Protection"),
        ("", ""),
    ],
)
def test_a_family_heading_normalizes_to_the_catalogs_spelling(value, expected):
    assert govramp.normalize_family(value) == expected


def test_an_enhancement_row_names_its_parent_first_and_itself_second():
    assert govramp.split_title("Account Management\nAutomated Register Upkeep") == (
        "Account Management",
        "Automated Register Upkeep",
    )


def test_a_base_control_row_has_only_the_one_name():
    assert govramp.split_title("Account Management") == ("Account Management", "")


# --------------------------------------------------------------------------
# The parameter cell
# --------------------------------------------------------------------------


def test_two_values_on_one_line_stay_one_decision():
    """`AC-1 (c) (2)` is one parameter with two halves. Split into two
    entries, the second would read as overriding the first."""
    parsed = govramp.parse_parameters("AC-1 (c) (2) [each full moon] [after any flood]")
    assert parsed == {"AC-1 (c) (2)": "each full moon; after any flood"}


def test_a_continuation_line_belongs_to_the_citation_above_it():
    """Read as an entry of its own it would key on the empty string and
    overwrite its neighbour."""
    parsed = govramp.parse_parameters(
        "AC-2 (2) [Selection: suspends] \n[Assignment: no more than two market days]"
    )
    assert parsed == {"AC-2 (2)": "Selection: suspends; Assignment: no more than two market days"}


def test_a_citation_with_no_space_before_its_bracket_still_parses():
    parsed = govramp.parse_parameters("AC-2 (12) (b)[at a minimum, the harbourmaster]")
    assert parsed == {"AC-2 (12) (b)": "at a minimum, the harbourmaster"}


def test_a_note_after_the_brackets_is_kept():
    """It points at the additional-requirements text this loader also
    captures, and dropping it severs the link between the two."""
    parsed = govramp.parse_parameters(
        "AC-2 (3) (d)[ninety (90) sunrises] (See additional requirements and guidance.)"
    )
    assert parsed == {
        "AC-2 (3) (d)": "ninety (90) sunrises (See additional requirements and guidance.)"
    }


def test_several_lines_become_several_parameters():
    parsed = govramp.parse_parameters(
        "AC-2 (h) (1) [one watch]\nAC-2 (h) (2) [two watches]\nAC-2 (j) [twice per cycle]"
    )
    assert parsed == {
        "AC-2 (h) (1)": "one watch",
        "AC-2 (h) (2)": "two watches",
        "AC-2 (j)": "twice per cycle",
    }


def test_an_empty_parameter_cell_yields_nothing():
    """Most rows have one: only 137 of the published Moderate matrix's 319
    controls define a parameter at all."""
    assert govramp.parse_parameters("") == {}
    assert govramp.parse_parameters("   \n  ") == {}


# --------------------------------------------------------------------------
# Tiers
# --------------------------------------------------------------------------


def test_the_baseline_carries_the_impact_level_and_the_tiers():
    """Both axes, impact level first, because consumers substring-match this
    field -- `--baseline moderate` and a filter for `core` both have to
    land."""
    label = govramp.baseline_label("Moderate", [CORE, READY, AUTHORIZED])
    assert label == "Moderate; Core, Ready, Authorized"
    assert "moderate" in label.lower()
    assert "Core" in label


def test_a_baseline_survives_half_an_answer():
    assert govramp.baseline_label("Moderate", []) == "Moderate"
    assert govramp.baseline_label("", [AUTHORIZED]) == "Authorized"


def test_intact_tier_columns_report_no_nesting_break(matrix):
    controls, rows = export.load_with_rows(matrix)
    assert govramp.tier_nesting_breaks(rows) == []
    assert controls  # the fixture parsed at all


def test_a_control_required_at_core_but_not_above_is_reported():
    """GovRAMP's tiers nest: Core inside Ready inside Authorized. A break
    means the three columns were misidentified -- swapped, or shifted one
    column left onto SORT ID -- and that failure is otherwise silent,
    because every count still looks plausible and every scope built on them
    is wrong.
    """
    row = govramp.Row(
        control_id="AC-2",
        tiers={CORE: True, READY: False, AUTHORIZED: True},
    )
    breaks = govramp.tier_nesting_breaks([row])
    assert len(breaks) == 1
    assert "AC-2" in breaks[0] and "Ready" in breaks[0]


# --------------------------------------------------------------------------
# Assembly
# --------------------------------------------------------------------------


def test_enhancements_fold_into_their_parent_control(matrix):
    """As `ControlEnhancement`, the schema's *additive* sub-requirement,
    which is what an 800-53 enhancement is. Modelled as `Requirement` --
    the alternative shape HITRUST needs -- every enhanced control would be
    double-counted in a coverage report."""
    controls = export.load(matrix)

    assert [c.control_id for c in controls] == ["AC-1", "AC-2", "SR-11"]
    ac2 = next(c for c in controls if c.control_id == "AC-2")
    assert [e.enhancement_id for e in ac2.enhancements] == ["AC-2(1)", "AC-2(2)", "AC-2(3)"]
    assert ac2.requirements == []


def test_an_enhancement_takes_its_own_name_not_its_parents(matrix):
    controls = export.load(matrix)
    ac2 = next(c for c in controls if c.control_id == "AC-2")
    assert ac2.title == "Account Management"
    assert ac2.enhancements[0].title == "Automated Register Upkeep"


def test_each_control_crosswalks_to_the_catalog_it_profiles(matrix):
    """GovRAMP is a profile, so its identifiers *are* 800-53's. This is the
    edge `policyforge map` needs, and it exists at the enhancement level
    too."""
    controls = export.load(matrix)
    ac2 = next(c for c in controls if c.control_id == "AC-2")

    assert ac2.source_crosswalk == {"NIST 800-53": "AC-2"}
    assert ac2.enhancements[0].source_crosswalk == {"NIST 800-53": "AC-2(1)"}


def test_a_control_carries_its_tier_and_its_impact_level(matrix):
    controls = export.load(matrix)
    ac1 = next(c for c in controls if c.control_id == "AC-1")
    ac2 = next(c for c in controls if c.control_id == "AC-2")

    # AC-1 is required only to reach Authorized; AC-2 from Core upward.
    assert ac1.baseline == "Moderate; Authorized"
    assert ac2.baseline == "Moderate; Core, Ready, Authorized"


def test_parameter_values_and_added_requirements_reach_the_control(matrix):
    """The two things a profile adds to the catalog it quotes, and the whole
    reason to ingest one rather than reading 800-53 directly."""
    controls = export.load(matrix)
    ac1 = next(c for c in controls if c.control_id == "AC-1")
    ac2 = next(c for c in controls if c.control_id == "AC-2")
    dormant = next(e for e in ac2.enhancements if e.enhancement_id == "AC-2(3)")

    assert ac1.parameter_values == {
        "AC-1 (c) (1)": "every other harvest",
        "AC-1 (c) (2)": "each full moon; after any flood",
    }
    assert "idleness period" in dormant.additional_requirements
    assert dormant.parameter_values["AC-2 (3) (d)"].startswith("ninety (90) sunrises")


def test_an_enhancement_without_its_base_control_still_lands():
    """The published matrices have no such row -- 800-53 does not select an
    enhancement without its base -- but a filtered or hand-trimmed export
    easily does, and the alternative is dropping it."""
    orphan = govramp.Row(
        control_id="AU-6 (3)",
        family="AUDIT AND ACCOUNTABILITY",
        name="Audit Record Review\nCorrelate Repositories",
        statement="Compare records across repositories.",
        tiers={AUTHORIZED: True},
    )
    controls = govramp.build_controls([orphan], impact_level="Moderate")

    assert len(controls) == 1
    assert controls[0].control_id == "AU-6"
    assert controls[0].title == "Audit Record Review"
    assert controls[0].family == "Audit and Accountability"
    assert [e.enhancement_id for e in controls[0].enhancements] == ["AU-6(3)"]


def test_blank_and_totals_rows_are_not_controls(matrix):
    """The workbook carries a totals row under the tier columns and a blank
    tail below it. Both arrive with no identifier."""
    controls, rows = export.load_with_rows(matrix)
    assert len(rows) == len(DATA_ROWS)
    assert all(row.is_populated for row in rows)
    assert sum(len(c.enhancements) for c in controls) + len(controls) == len(DATA_ROWS)


# --------------------------------------------------------------------------
# Reading the workbook
# --------------------------------------------------------------------------


def test_a_two_row_header_merges_into_one_caption_per_column():
    """openpyxl reports a merged span as `None` everywhere but its first
    cell, so a group title contributes to one column and blanks contribute
    nothing."""
    merged = export.merge_header([GROUP_ROW, CAPTION_ROW])
    assert merged[0].startswith("Control Information")
    assert merged[1] == "Required for Core"
    assert merged[8].startswith("GovRAMP Parameters")


def test_the_controls_sheet_is_found_by_its_captions_not_its_name(tmp_path):
    """The sheet number is a position in a template GovRAMP renumbers
    between revisions, and the Low and High workbooks name it differently.
    Detection by caption is what lets all three through with no special
    case."""
    renamed = build_workbook(
        tmp_path / "GovRAMP-Controls-Matrix_High_Rev5_V2.0.xlsx",
        controls_sheet_name="9_Something Else Entirely",
    )
    controls = export.load(renamed)
    assert [c.control_id for c in controls] == ["AC-1", "AC-2", "SR-11"]


def test_a_caption_that_grows_a_parenthetical_still_resolves(matrix):
    """The caption reads `NIST Control Description\\n (From NIST SP 800-53r5
    12/10/2020)` and carries a date that will change, so matching is on a
    normalized substring rather than the whole caption."""
    controls = export.load(matrix)
    ac1 = next(c for c in controls if c.control_id == "AC-1")
    assert ac1.control_statement.startswith("a. Publish an access policy")
    assert ac1.discussion == "A policy says who decides."


def test_the_bare_id_caption_does_not_claim_the_sort_id_column(matrix):
    """The caption `ID` is a substring of `SORT ID`. Claimed in the wrong
    order, every control id would be the zero-padded sort spelling and
    nothing would join to 800-53."""
    columns = export.detect_columns(export.merge_header([GROUP_ROW, CAPTION_ROW]))
    assert columns["sort_id"] == 4
    assert columns["control_id"] == 6


def test_a_workbook_missing_a_required_column_says_which(tmp_path):
    """Failing with a list of missing fields is the point. A heuristic that
    quietly returned two thirds of a baseline would be read as a smaller
    baseline, and a scope is the one thing nobody re-checks by hand."""
    captions = list(CAPTION_ROW)
    captions[1] = "Notes"  # "Required for Core" gone
    stripped = build_workbook(tmp_path / "trimmed.xlsx", caption_row=captions)

    with pytest.raises(export.ExportFormatError) as raised:
        export.load(stripped)
    assert "tier_core" in str(raised.value)


def test_a_workbook_that_is_not_a_controls_matrix_is_refused(tmp_path):
    book = Workbook()
    book.active.append(["alpha", "beta"])
    book.active.append(["1", "2"])
    path = tmp_path / "unrelated.xlsx"
    book.save(path)

    with pytest.raises(export.ExportFormatError) as raised:
        export.load(path)
    assert "GovRAMP controls matrix" in str(raised.value)


def test_a_file_that_is_not_a_workbook_is_refused(tmp_path):
    path = tmp_path / "matrix.csv"
    path.write_text("ID,Control Name\nAC-1,Policy\n", encoding="utf-8")

    with pytest.raises(export.ExportFormatError) as raised:
        export.load(path)
    assert ".xlsx" in str(raised.value)


# --------------------------------------------------------------------------
# Workbook metadata
# --------------------------------------------------------------------------


def test_the_impact_level_and_revision_come_from_the_cover_sheet(matrix):
    controls = export.load(matrix)
    assert controls[0].baseline.startswith("Moderate")
    assert controls[0].framework_version == "Rev 5 (V1.06)"


def test_the_workbook_outranks_the_filename_for_the_impact_level(tmp_path):
    """A file somebody renamed is a weaker claim than what the workbook
    says about itself, so the cover sheet and the instructions are read
    first."""
    path = build_workbook(tmp_path / "GovRAMP-Controls-Matrix_High_Rev5_V1.06.xlsx")
    assert export.load(path)[0].baseline.startswith("Moderate")


def test_the_filename_is_the_fallback_when_the_workbook_says_nothing(tmp_path):
    """The cover sheet is the first thing edited once somebody starts
    working in the template, and the instructions page goes with it."""
    path = build_workbook(
        tmp_path / "GovRAMP-Controls-Matrix_High_Rev5_V1.06.xlsx",
        cover=("{Service Provider Name}",),
        instructions=(),
    )
    controls = export.load(path)
    assert controls[0].baseline.startswith("High")


def test_an_explicit_impact_level_overrides_the_file(matrix):
    controls = export.load(matrix, impact_level="High")
    assert controls[0].baseline.startswith("High")


@pytest.mark.parametrize(
    ("stem", "expected"),
    [
        ("GovRAMP-Controls-Matrix_Mod_Rev5_V1.06", "Moderate"),
        ("GovRAMP-Controls-Matrix_High_Rev5_V1.06", "High"),
        ("GovRAMP-Controls-Matrix_Low_Rev5_V1.06", "Low"),
        ("some-other-workbook", ""),
    ],
)
def test_the_impact_level_reads_out_of_a_filename(tmp_path, stem, expected):
    assert export.impact_level_from_name(tmp_path / f"{stem}.xlsx") == expected


def test_the_template_version_reads_out_of_a_filename(tmp_path):
    assert export.version_from_name(tmp_path / "GovRAMP-Matrix_Rev5_V1.06.xlsx") == "V1.06"


# --------------------------------------------------------------------------
# Reporting
# --------------------------------------------------------------------------


def test_a_summary_counts_what_was_parsed(matrix):
    controls, rows = export.load_with_rows(matrix)
    summary = govramp.summarize(controls, rows=rows)

    assert summary.controls == 3
    assert summary.enhancements == 3
    assert summary.impact_level == "Moderate"
    assert summary.tiers[CORE] == 2
    assert summary.tiers[AUTHORIZED] == 6
    assert summary.parameters == 5
    assert summary.guidance_blocks == 1

    # No *structural* complaint: every column was found. The one warning
    # this fixture does earn is the size check below, which fires because
    # six rows labelled Moderate really would be a half-read sheet if they
    # came from a real matrix.
    assert not [w for w in summary.warnings if "column" in w or "tier" in w]


def test_a_short_moderate_catalog_reads_as_a_partial_parse(matrix):
    """The failure this guards against is not an exception. It is a
    plausible catalog: a sheet read down to the row where something went
    wrong still has correct-looking families, tiers and parameters, and only
    the count gives it away. A smaller *baseline* is the innocent
    explanation, which is why the warning names the alternative rather than
    raising.
    """
    controls, rows = export.load_with_rows(matrix)
    warnings = " ".join(govramp.summarize(controls, rows=rows).warnings)

    assert "partial read" in warnings
    assert "319" in warnings


def test_a_summary_reports_its_counts_in_the_printed_form(matrix):
    controls, rows = export.load_with_rows(matrix)
    report = govramp.summarize(controls, rows=rows).format_report()

    assert "GovRAMP Rev 5 (V1.06) Moderate" in report
    assert "3 controls, 3 enhancements" in report
    assert "Core" in report and "Authorized" in report


def test_a_catalog_with_no_tier_marked_warns():
    """The failure mode of a heuristic loader is not an exception but a
    plausible catalog with a column missing."""
    row = govramp.Row(control_id="AC-1", name="Policy", statement="Publish a policy.")
    controls = govramp.build_controls([row], impact_level="Moderate")
    warnings = " ".join(govramp.summarize(controls).warnings)

    assert "Core/Ready/Authorized" in warnings


def test_a_catalog_with_no_parameter_values_warns():
    """Without them the catalog is 800-53 with a baseline column, which the
    bundled data already provides."""
    row = govramp.Row(
        control_id="AC-1",
        name="Policy",
        statement="Publish a policy.",
        tiers={CORE: True, READY: True, AUTHORIZED: True},
    )
    controls = govramp.build_controls([row], impact_level="Moderate")
    warnings = " ".join(govramp.summarize(controls).warnings)

    assert "parameter values" in warnings


def test_a_misaligned_tier_column_surfaces_as_a_warning():
    rows = [
        govramp.Row(
            control_id="AC-1",
            name="Policy",
            statement="Publish a policy.",
            parameters="AC-1 (a) [each full moon]",
            tiers={CORE: True, READY: False, AUTHORIZED: True},
        )
    ]
    controls = govramp.build_controls(rows, impact_level="Moderate")
    warnings = " ".join(govramp.summarize(controls, rows=rows).warnings)

    assert "stricter tier" in warnings


# --------------------------------------------------------------------------
# The rest of the pipeline
# --------------------------------------------------------------------------


def test_a_parsed_catalog_round_trips_through_the_schema(matrix, tmp_path):
    """`etl-govramp --out` writes with `dataclasses.asdict` and every later
    command reads with `load_controls`. The two new fields have to survive
    that, or the parameter values exist only in the ETL run that made
    them."""
    import dataclasses
    import json

    from policyforge.ingest.schema import load_controls

    controls = export.load(matrix)
    path = tmp_path / "controls.json"
    path.write_text(
        json.dumps([dataclasses.asdict(c) for c in controls], indent=2), encoding="utf-8"
    )

    reloaded = load_controls(path)
    ac1 = next(c for c in reloaded if c.control_id == "AC-1")
    ac2 = next(c for c in reloaded if c.control_id == "AC-2")

    assert ac1.parameter_values["AC-1 (c) (1)"] == "every other harvest"
    assert ac2.enhancements[0].enhancement_id == "AC-2(1)"
    assert next(
        e for e in ac2.enhancements if e.enhancement_id == "AC-2(3)"
    ).additional_requirements


def test_a_catalog_written_before_these_fields_existed_still_loads(tmp_path):
    """Files on disk outlive the schema that wrote them, and re-running an
    ETL to read an old catalog is a poor trade for a default."""
    import json

    from policyforge.ingest.schema import load_controls

    path = tmp_path / "old.json"
    path.write_text(
        json.dumps(
            [
                {
                    "control_id": "AC-1",
                    "title": "Policy and Procedures",
                    "framework": "GovRAMP",
                    "framework_version": "Rev 5",
                }
            ]
        ),
        encoding="utf-8",
    )

    control = load_controls(path)[0]
    assert control.parameter_values == {}
    assert control.additional_requirements == ""


def test_govramp_controls_crosswalk_onto_their_nist_anchors(matrix):
    """The end of the integration: `policyforge map` has to come back with
    govramp among the frameworks it mapped, at both the control and the
    enhancement level."""
    from policyforge.ingest.schema import Control
    from policyforge.mapping.crosswalk import build_crosswalk

    govramp_controls = export.load(matrix)
    nist = [
        Control(
            control_id="AC-2",
            title="Account Management",
            framework="NIST 800-53",
            framework_version="Rev 5",
        )
    ]

    crosswalk = build_crosswalk(nist + govramp_controls)

    assert crosswalk["AC-2"]["govramp"] == ["AC-2"]
    assert crosswalk["AC-2(1)"]["govramp"] == ["AC-2(1)"]
    assert crosswalk["SR-11"]["govramp"] == ["SR-11"]


def test_the_baseline_filter_the_cli_uses_selects_govramp_controls(matrix):
    """`--baseline moderate` substring-matches `Control.baseline`, which is
    the same test `ssp`, `parameters` and the shell's `/coverage` apply. A
    baseline string those miss would silently scope every report to
    nothing."""
    controls = export.load(matrix)

    moderate = [c for c in controls if c.baseline and "moderate" in c.baseline.lower()]
    core = [c for c in controls if c.baseline and "core" in c.baseline.lower()]

    assert len(moderate) == 3
    assert [c.control_id for c in core] == ["AC-2"]


def test_a_profiles_additions_reach_the_synthesis_prompt(matrix):
    """Parameter values and added requirements are handed to the model, not
    dropped. Without them the model fills `[Assignment: ...]` by guessing,
    which is the failure `parameters/ledger.py` exists to prevent."""
    from policyforge.synthesis.merge import _render_control

    controls = export.load(matrix)
    rendered = _render_control(next(c for c in controls if c.control_id == "AC-1"))

    assert "Framework-defined parameter values" in rendered
    assert "every other harvest" in rendered

    ac2 = _render_control(next(c for c in controls if c.control_id == "AC-2"))
    assert "Additional framework requirements" in ac2
    assert "idleness period" in ac2
