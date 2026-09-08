"""HITRUST CSF structure, and reading it out of the files it arrives in.

Every fixture here is invented. The shape is modelled on a MyCSF SSRS
export -- the meaningless `Textbox` column names, the caption column beside
each value, the whole-row duplication, the 36-character truncation of the
level column -- but the control text, the identifiers and the authoritative
sources are made up. That is deliberate and not merely cautious: HITRUST
CSF is licensed content, this repository is public, and a fixture is a file
that gets committed.

It also makes the tests better. A fixture built to exercise the awkward
cases (a category id that prefixes an objective id, a source name that is
also the prefix of another source name) exercises them reliably, which a
sample of real rows would only do by luck.
"""

from __future__ import annotations

import pytest

from policyforge.ingest import hitrust
from policyforge.ingest import hitrust_export as export
from policyforge.ingest.schema import MATURITY, OVERLAY

# --------------------------------------------------------------------------
# Tier identifiers
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("01.a Access Control Policy", ("01.a", "Access Control Policy")),
        ("00.a Programme Definition", ("00.a", "Programme Definition")),
        ("09.aa Logging", ("09.aa", "Logging")),
        ("  07.c  Spaced Title  ", ("07.c", "Spaced Title")),
    ],
)
def test_a_control_reference_splits_into_id_and_title(value, expected):
    assert hitrust.parse_reference(value) == expected


def test_a_category_id_does_not_swallow_an_objective():
    """`01.0` is a prefix of `01.01`, and the naive pattern matches both.

    Column detection identifies the category column by counting how many of
    its values look like a category. Without the boundary, the objective
    column looks exactly as much like one, detection picks whichever comes
    first, and 49 objectives collapse into 14 categories with no error
    anywhere.
    """
    assert hitrust.parse_category("01.0 - Access Control") == ("01.0", "Access Control")
    assert hitrust.CATEGORY_RE.match("01.01 Business Requirement") is None
    assert hitrust.parse_objective("01.01 Business Requirement") == (
        "01.01",
        "Business Requirement",
    )


def test_an_unparseable_tier_keeps_its_text_rather_than_vanishing():
    """A title with no identifier is still a title. Returning ("", "") would
    silently drop a control reference from the catalog."""
    assert hitrust.parse_reference("Unnumbered Control") == ("", "Unnumbered Control")


# --------------------------------------------------------------------------
# Levels
# --------------------------------------------------------------------------


@pytest.mark.parametrize("label", ["Level 1", "Level 2", "Level 3"])
def test_the_numbered_levels_are_the_maturity_ladder(label):
    assert hitrust.parse_level(label) == (label, MATURITY)


@pytest.mark.parametrize(
    "label",
    ["Level HIPAA", "Level FedRAMP", "Level FTI Custodians", "Level Some New Regulation"],
)
def test_every_other_level_is_an_overlay(label):
    """Including levels nobody has seen before.

    HITRUST adds regulatory levels between releases. An unknown level read
    as maturity would join an ordered ladder it has no place on, so the
    default has to fall the other way.
    """
    assert hitrust.parse_level(label) == (label, OVERLAY)


def test_a_truncated_level_name_is_recovered_from_a_longer_one():
    """The CSV cuts the level column at 36 characters; the caption columns
    beside it do not. Left unmerged, one level becomes two."""
    clipped = "Level Digital Personal Data Protecti"
    full = "Level Digital Personal Data Protection Act"
    resolved = hitrust.merge_level_names([clipped, full, "Level 1"])

    assert resolved[clipped] == full
    assert resolved[full] == full
    assert resolved["Level 1"] == "Level 1"


def test_level_names_that_merely_share_a_prefix_are_left_alone():
    resolved = hitrust.merge_level_names(["Level 1", "Level 2"])
    assert resolved == {"Level 1": "Level 1", "Level 2": "Level 2"}


# --------------------------------------------------------------------------
# The authoritative-source crosswalk
# --------------------------------------------------------------------------

#: Invented sources, chosen to reproduce the three ways a mapping line is
#: genuinely ambiguous: a publisher with several standards under it
#: (`ACME`), a source whose name ends in a number (`ACME 9000:2020`), and
#: identifiers that contain spaces and brackets.
_MAPPING_LINES = [
    "ACME 9000:2020 4.1a",
    "ACME 9000:2020 4.2b",
    "ACME 9000:2020 5.1",
    "ACME 9000:2020 5.2",
    "ACME 9000:2020 6.1",
    "ACME 9000:2020 6.2",
    "ACME 9000:2020 7.3",
    "Bureau of Examples Directive BOE-1",
    "Bureau of Examples Directive BOE-2",
    "Bureau of Examples Directive BOE-3",
    "Bureau of Examples Directive BOE-4",
    "Bureau of Examples Directive BOE-5",
    "Bureau of Examples Directive BOE-6",
    "Bureau of Examples Directive BOE-7",
]


def test_source_names_are_learned_from_the_export():
    """No vocabulary is shipped, so a source is whatever the file evidences."""
    sources = hitrust.learn_sources(_MAPPING_LINES)

    assert "Bureau of Examples Directive" in sources
    assert "ACME 9000:2020" in sources


def test_a_standard_number_stays_with_its_publisher():
    """A publisher that issues many standards branches at the point its name
    is still incomplete.

    `ACME` is followed by six different standard numbers, which is exactly
    the signal that ends a source name -- and ending it there would file
    9000:2020 and 9001:2020 under one source called `ACME`, collapsing two
    frameworks into one.
    """
    lines = _MAPPING_LINES + [f"ACME 900{n}:2020 {n}.{n}" for n in range(1, 8)]
    sources = hitrust.learn_sources(lines)

    assert "ACME" not in sources
    assert any(s.startswith("ACME 900") for s in sources)


def test_a_mapping_line_splits_on_the_longest_matching_source():
    sources = {"ACME", "ACME 9000:2020"}
    assert hitrust.split_mapping("ACME 9000:2020 4.1a", sources) == ("ACME 9000:2020", "4.1a")


def test_a_source_only_matches_on_a_token_boundary():
    """`ACME 900` must not claim a line about `ACME 9000`."""
    assert hitrust.split_mapping("ACME 9000 X-1", {"ACME 900"}) == ("", "ACME 9000 X-1")


def test_an_unrecognised_line_keeps_its_whole_text():
    """Filed under no source rather than guessed into the wrong one."""
    source, identifier = hitrust.split_mapping("Something Unseen 1.1", set())
    assert source == ""
    assert identifier == "Something Unseen 1.1"


def test_mappings_group_by_source_and_drop_repeats():
    sources = hitrust.learn_sources(_MAPPING_LINES)
    cell = "ACME 9000:2020 4.1a\r\nACME 9000:2020 4.1a\r\nBureau of Examples Directive BOE-1"

    grouped = hitrust.build_mappings(cell, sources)

    assert grouped["ACME 9000:2020"] == ["4.1a"]
    assert grouped["Bureau of Examples Directive"] == ["BOE-1"]


# --------------------------------------------------------------------------
# Records -> Controls
# --------------------------------------------------------------------------


def _record(**overrides):
    values = {
        "category": "01.0 - Example Category",
        "objective": "01.01 Example Objective",
        "objective_statement": "To do the example thing.",
        "reference": "01.a Example Control",
        "specification": "The organization shall do the example thing.",
        "factor_type": "Organizational",
        "level": "Level 1",
        "statement": "The example thing is documented.",
        "mapping": "ACME 9000:2020 4.1a",
    }
    values.update(overrides)
    return hitrust.Record(**values)


def test_identical_rows_collapse_to_one_record():
    """A v11.7 CSV holds 2,818 rows for 1,219 records. Counted rather than
    collapsed, every coverage and mapping total is inflated."""
    assert len(hitrust.dedupe([_record(), _record(), _record()])) == 1


def test_rows_for_different_levels_are_different_records():
    records = hitrust.dedupe([_record(), _record(level="Level 2")])
    assert len(records) == 2


def test_a_row_missing_its_key_is_dropped():
    """A record with no reference or no level cannot be placed under a
    control, and keeping it would put an unattributed requirement in the
    catalog."""
    assert hitrust.dedupe([_record(reference=""), _record(level="")]) == []


def test_the_longer_statement_wins_a_collision():
    records = hitrust.dedupe(
        [_record(statement="Short."), _record(statement="A considerably longer statement.")]
    )
    assert records[0].statement == "A considerably longer statement."


def test_a_control_carries_its_whole_hierarchy():
    (control,) = hitrust.build_controls([_record()], version="v11.7")

    assert control.control_id == "01.a"
    assert control.title == "Example Control"
    assert control.family_abbr == "01.0"
    assert control.family == "Example Category"
    assert control.objective_id == "01.01"
    assert control.objective_title == "Example Objective"
    assert control.objective_statement == "To do the example thing."
    assert control.factor_type == "Organizational"
    assert control.framework == hitrust.FRAMEWORK
    assert control.framework_version == "v11.7"


def test_levels_become_requirements_not_enhancements():
    """The distinction the schema exists to preserve. An overlay is a
    parallel statement selected by a scoping factor, not extra rigour added
    on top of Level 1."""
    (control,) = hitrust.build_controls(
        [_record(), _record(level="Level HIPAA", statement="The HIPAA wording.")]
    )

    assert control.enhancements == []
    assert [r.level for r in control.requirements] == ["Level 1", "Level HIPAA"]
    assert [r.level_kind for r in control.requirements] == [MATURITY, OVERLAY]


def test_requirements_are_ordered_maturity_first():
    """So the ladder reads as a ladder however the report emitted the rows."""
    (control,) = hitrust.build_controls(
        [
            _record(level="Level PCI"),
            _record(level="Level 2"),
            _record(level="Level ACME"),
            _record(level="Level 1"),
        ]
    )
    assert [r.level for r in control.requirements] == [
        "Level 1",
        "Level 2",
        "Level ACME",
        "Level PCI",
    ]


def test_one_control_gathers_every_level_of_its_reference():
    controls = hitrust.build_controls(
        [_record(), _record(level="Level 2"), _record(reference="01.b Another Control")]
    )
    by_id = {c.control_id: c for c in controls}

    assert len(by_id["01.a"].requirements) == 2
    assert len(by_id["01.b"].requirements) == 1


def test_factor_cells_become_lists():
    (control,) = hitrust.build_controls(
        [
            _record(
                organizational_factors="Size: Large\r\nSize: Very Large",
                system_factors="Applicable to all systems",
            )
        ]
    )
    requirement = control.requirements[0]

    assert requirement.organizational_factors == ["Size: Large", "Size: Very Large"]
    assert requirement.system_factors == ["Applicable to all systems"]
    assert requirement.regulatory_factors == []


def test_a_requirement_id_names_its_control_and_level():
    (control,) = hitrust.build_controls([_record(level="Level FedRAMP")])
    assert control.requirements[0].requirement_id == "01.a Level FedRAMP"


# --------------------------------------------------------------------------
# Summary
# --------------------------------------------------------------------------


def test_a_thin_parse_is_reported_rather_than_returned_quietly():
    """The failure mode of a heuristic loader is a plausible catalog missing
    two thirds of the library, which no exception marks."""
    summary = hitrust.summarize(hitrust.build_controls([_record()]))

    assert summary.references == 1
    assert any("references parsed" in w for w in summary.warnings)


def test_a_parse_with_no_mappings_says_so():
    summary = hitrust.summarize(hitrust.build_controls([_record(mapping="")]))
    assert any("no authoritative-source mappings" in w for w in summary.warnings)


def test_a_parse_with_no_maturity_levels_says_so():
    summary = hitrust.summarize(hitrust.build_controls([_record(level="Level PCI")]))
    assert any("no Level 1/2/3" in w for w in summary.warnings)


# --------------------------------------------------------------------------
# Column detection
# --------------------------------------------------------------------------

#: A MyCSF CSV, in miniature: SSRS textbox names for headers, a caption
#: column immediately before each value column it describes, and one row per
#: (reference x level) with the tiers repeated.
_SSRS_HEADER = [
    "Control_Category",
    "Objective_Name",
    "Objective_Description",
    "Textbox52",
    "Control_Specification",
    "Type",
    "Textbox108",
    "Textbox104",
    "Textbox105",
    "Textbox110",
    "Level_Implementation",
    "Textbox47",
    "Standard_Mapping",
]


def _ssrs_row(level="Level 1", statement="The example thing is documented."):
    return [
        "01.0 - Example Category",
        "01.01 Example Objective",
        "To do the example thing.",
        "01.a Example Control",
        "The organization shall do the example thing.",
        "Organizational",
        level,
        f"{level} \r\nOrganizational Factors:",
        "Size: Large",
        f"{level} Implementation:",
        statement,
        f"{level} \r\nControl Standard \r\nMapping:",
        "ACME 9000:2020 4.1a",
    ]


def test_columns_are_found_despite_meaningless_headers():
    """`Textbox52` says nothing. The column is identified by holding values
    shaped like `01.a Example Control`."""
    rows = [_ssrs_row(), _ssrs_row("Level 2")]
    fields = export.detect_fields(_SSRS_HEADER, rows)

    assert fields["reference"] == _SSRS_HEADER.index("Textbox52")
    assert fields["level"] == _SSRS_HEADER.index("Textbox108")


def test_a_caption_column_names_the_column_after_it():
    """The export documents itself one column to the left: `Textbox104`
    holds nothing but "Level 1 Organizational Factors:"."""
    rows = [_ssrs_row(), _ssrs_row("Level 2")]
    fields = export.detect_fields(_SSRS_HEADER, rows)

    assert fields["organizational_factors"] == _SSRS_HEADER.index("Textbox105")


def test_a_real_header_beats_a_guess_about_content():
    rows = [_ssrs_row()]
    fields = export.detect_fields(_SSRS_HEADER, rows)

    assert fields["category"] == _SSRS_HEADER.index("Control_Category")
    assert fields["objective"] == _SSRS_HEADER.index("Objective_Name")
    assert fields["specification"] == _SSRS_HEADER.index("Control_Specification")


def test_an_export_missing_a_required_field_is_refused_by_name():
    """Returning a partial catalog would be read as a small framework."""
    with pytest.raises(export.ExportFormatError) as raised:
        export.records_from_table(["alpha", "beta"], [["1", "2"]])

    assert "reference" in str(raised.value)


def test_a_csv_export_round_trips(tmp_path):
    import csv

    path = tmp_path / "CSFLibraryReport.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(_SSRS_HEADER)
        # Duplicated deliberately: this is what the report does.
        for row in (_ssrs_row(), _ssrs_row(), _ssrs_row("Level 2")):
            writer.writerow(row)

    controls = export.load(path)

    assert len(controls) == 1
    assert [r.level for r in controls[0].requirements] == ["Level 1", "Level 2"]
    assert controls[0].requirements[0].mappings == {"ACME 9000:2020": ["4.1a"]}


def test_a_version_is_read_from_the_filename(tmp_path):
    """A MyCSF export states its CSF release nowhere inside the file."""
    assert export.version_from_name(tmp_path / "CSFLibraryReport_v11.7.csv") == "v11.7"
    assert export.version_from_name(tmp_path / "CSFLibraryReport.csv") == ""


def test_an_unsupported_format_is_refused(tmp_path):
    path = tmp_path / "export.pdf"
    path.write_bytes(b"%PDF-1.4")

    with pytest.raises(export.ExportFormatError):
        export.read_records(path)


# --------------------------------------------------------------------------
# Rendered reports
# --------------------------------------------------------------------------

_RENDERED = """
<html><body><table>
<tr><td>Control Category:</td><td>01.0 - Example Category</td></tr>
<tr><td>Objective Name:</td><td>01.01 Example Objective</td></tr>
<tr><td>Control Objective:</td><td>To do the example thing.</td></tr>
<tr><td>Control Reference:</td><td>01.a Example Control</td></tr>
<tr><td>Control Specification:</td><td>The organization shall do it.</td></tr>
<tr><td>Factor Type:</td><td>Organizational</td></tr>
<tr><td>Level 1</td><td>Implementation Requirements</td></tr>
<tr><td>Level 1 Organizational Factors:</td><td>Size: Large<br/>Size: Very Large</td></tr>
<tr><td>Level 1 Implementation:</td><td>The example thing is documented.</td></tr>
<tr><td>Level 1 Control Standard Mapping:</td>
<td>ACME 9000:2020 4.1a<br/>ACME 9000:2020 4.2b</td></tr>
<tr><td>Level 2 Implementation:</td><td>The example thing is reviewed.</td></tr>
</table></body></html>
"""


def test_a_rendered_report_reads_from_its_labels():
    records = export.records_from_markup(_RENDERED)
    controls = hitrust.build_controls(records)

    assert len(controls) == 1
    control = controls[0]
    assert control.control_id == "01.a"
    assert control.objective_id == "01.01"
    assert [r.level for r in control.requirements] == ["Level 1", "Level 2"]


def test_a_br_separated_cell_becomes_a_list():
    (control,) = hitrust.build_controls(export.records_from_markup(_RENDERED))
    level_one = control.requirements[0]

    assert level_one.organizational_factors == ["Size: Large", "Size: Very Large"]
    assert level_one.mappings["ACME 9000:2020"] == ["4.1a", "4.2b"]


def test_a_cell_split_across_a_page_break_is_rejoined():
    """SSRS re-prints a label when a long cell crosses a page boundary.
    Overwriting on the second row would keep only its tail."""
    markup = _RENDERED.replace(
        "<tr><td>Level 2 Implementation:</td><td>The example thing is reviewed.</td></tr>",
        "<tr><td>Level 1 Control Standard Mapping:</td><td>ACME 9000:2020 5.1</td></tr>",
    )
    (control,) = hitrust.build_controls(export.records_from_markup(markup))

    assert control.requirements[0].mappings["ACME 9000:2020"] == ["4.1a", "4.2b", "5.1"]


def test_a_report_with_no_hitrust_labels_is_refused():
    with pytest.raises(export.ExportFormatError):
        export.records_from_markup(
            "<html><body><table><tr><td>a</td><td>b</td></tr></table></body></html>"
        )


def test_an_mhtml_envelope_is_decoded(tmp_path):
    """MyCSF's MHTML is one base64 text/html part in a multipart/related
    envelope -- SSRS's "web archive" render."""
    import base64

    encoded = base64.b64encode(_RENDERED.encode("utf-8")).decode("ascii")
    path = tmp_path / "CSFLibraryReport.mhtml"
    path.write_text(
        "MIME-Version: 1.0\n"
        'Content-Type: multipart/related; boundary="--=_Part"\n\n'
        "----=_Part\n"
        'Content-Type: text/html; charset="utf-8"\n'
        "Content-Transfer-Encoding: base64\n\n"
        f"{encoded}\n"
        "----=_Part--\n",
        encoding="utf-8",
    )

    controls = export.load(path)
    assert [c.control_id for c in controls] == ["01.a"]


# --------------------------------------------------------------------------
# Reaching the crosswalk
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("NIST SP 800-53 r5", "nist"),
        ("NIST SP 800-53 r4", "nist"),
        ("NIST SP 800-171 r2", "nist-800-171"),
        ("NIST Cybersecurity Framework 2.0", "nist-csf"),
        ("HIPAA Security Rule", "hipaa"),
        ("HIPAA Privacy Rule", "hipaa-privacy"),
        ("CMS ARC-AMPE", "arc-ampe"),
        ("FedRAMP r5", "fedramp"),
    ],
)
def test_a_nist_family_is_not_one_framework(source, expected):
    """The "NIST" prefix spans 800-53, 800-171 and the Cybersecurity Framework, whose
    identifiers look nothing alike -- `AC-2`, `3.12.4[g]`, `GV.PO-02`.
    Keeping only the first word of the source name files CSF outcome ids as
    800-53 controls."""
    from policyforge.mapping.crosswalk import hitrust_framework

    assert hitrust_framework(source) == expected


def test_a_requirement_keeps_its_own_mappings():
    """HITRUST publishes its crosswalk per requirement statement, because
    two levels of one control reference map to different places."""
    from policyforge.mapping.crosswalk import requirement_crosswalk

    controls = hitrust.build_controls(
        [
            _record(mapping="NIST SP 800-53 r5 AC-1\nNIST SP 800-53 r5 AC-2"),
            _record(level="Level 2", mapping="NIST SP 800-53 r5 AC-3"),
        ]
    )
    table = requirement_crosswalk(controls)

    assert table["01.a Level 1"]["nist"] == ["AC-1", "AC-2"]
    assert table["01.a Level 2"]["nist"] == ["AC-3"]


def test_the_nist_anchored_table_records_the_level_that_earned_the_mapping():
    from policyforge.mapping.crosswalk import build_crosswalk

    controls = hitrust.build_controls(
        [
            _record(mapping="NIST SP 800-53 r5 AC-1"),
            _record(level="Level FedRAMP", mapping="NIST SP 800-53 r5 AC-1"),
        ]
    )
    crosswalk = build_crosswalk(controls)

    assert crosswalk["AC-1"]["hitrust-csf"] == ["01.a Level 1", "01.a Level FedRAMP"]


def test_a_non_800_53_source_never_anchors_a_row():
    """The crosswalk is 800-53-anchored by construction. A CSF outcome id
    is not an anchor however much `GV.PO-02` resembles one."""
    from policyforge.mapping.crosswalk import build_crosswalk

    controls = hitrust.build_controls(
        [_record(mapping="NIST Cybersecurity Framework 2.0 GV.PO-02")]
    )
    assert build_crosswalk(controls) == {}
