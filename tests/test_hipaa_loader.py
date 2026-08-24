"""ingest/hipaa_loader.py tests, against a real eCFR fixture (45 CFR 164
Subpart C, tests/fixtures/ecfr_45cfr164_subpart_c.xml — the actual
regulation text as fetched from eCFR's versioner API, not synthetic data).
Expected values here were hand-verified against that fixture's text."""

from __future__ import annotations

from pathlib import Path

FIXTURE = Path(__file__).parent / "fixtures" / "ecfr_45cfr164_subpart_c.xml"


def _load():
    from policyforge.ingest.hipaa_loader import parse_hipaa_security_rule

    xml = FIXTURE.read_text(encoding="utf-8")
    controls = parse_hipaa_security_rule(xml)
    by_id = {}
    for c in controls:
        by_id[c.control_id] = c
        for e in c.enhancements:
            by_id[e.enhancement_id] = e
    return controls, by_id


def test_parses_expected_number_of_controls():
    controls, _ = _load()
    # 34 top-level items across §164.306-318 (Definitions excluded).
    assert len(controls) == 34


def test_excludes_definitions_section():
    controls, _ = _load()
    assert not any(c.control_id.startswith("164.304") for c in controls)
    assert not any(c.title == "Access" for c in controls)  # a defined term, not a control


def test_security_management_process_standard_and_specs():
    _, by_id = _load()

    standard = by_id["164.308(a)(1)(i)"]
    assert standard.title == "Security management process"
    assert standard.framework == "HIPAA Security Rule"
    assert "prevent, detect, contain, and correct" in standard.control_statement
    assert [e.enhancement_id for e in standard.enhancements] == [
        "164.308(a)(1)(ii)(A)",
        "164.308(a)(1)(ii)(B)",
        "164.308(a)(1)(ii)(C)",
        "164.308(a)(1)(ii)(D)",
    ]

    risk_analysis = by_id["164.308(a)(1)(ii)(A)"]
    assert risk_analysis.title == "Risk analysis"
    assert risk_analysis.baseline == "Required"
    assert "potential risks and vulnerabilities" in risk_analysis.description


def test_workforce_security_specs_are_addressable():
    _, by_id = _load()
    spec = by_id["164.308(a)(3)(ii)(A)"]
    assert spec.title == "Authorization and/or supervision"
    assert spec.baseline == "Addressable"


def test_implementation_specs_marked_required_at_roman_level_not_just_capital():
    """§164.310 tags Required/Addressable at the roman-numeral level
    directly (no capital-letter sub-level), unlike §164.308 — the loader
    must not assume a fixed citation depth for specs."""
    _, by_id = _load()
    spec = by_id["164.310(d)(2)(i)"]
    assert spec.title == "Disposal"
    assert spec.baseline == "Required"


def test_ambiguous_letter_after_number_resolves_to_new_top_level_paragraph():
    """§164.312(d) ('Person or entity authentication') follows §164.312(c)(2)
    — a lone lowercase 'd' here must resolve to a new top-level paragraph,
    not a stray roman/capital numeral nested under (c)(2)."""
    _, by_id = _load()
    control = by_id["164.312(d)"]
    assert control.title == "Person or entity authentication"
    assert control.control_id == "164.312(d)"


def test_compound_paragraph_with_embedded_em_dash_citation_splits_correctly():
    """§164.314(a)(2) reads '(2) Implementation specifications (Required)
    —(i) Business associate contracts...' as a single <P> — the embedded
    '(i)' citation must still be recognized and tracked."""
    _, by_id = _load()
    assert "164.314(a)(2)(i)" in by_id
    contract = by_id["164.314(a)(2)(i)"]
    assert contract.title == "Business associate contracts"


def test_uncaptioned_list_items_are_appended_not_dropped():
    """The bare, un-italicized (A)/(B)/(C) list items under
    §164.314(a)(2)(i) carry real requirement text and must not be
    silently discarded just because they lack their own <I> lead-in."""
    _, by_id = _load()
    text = by_id["164.314(a)(2)(i)"].control_statement
    assert "Comply with the applicable requirements of this subpart" in text
    assert "Report to the covered entity any security incident" in text


def test_alternative_compliance_paths_are_separate_controls():
    """§164.314(a)(1) says the contract 'must meet the requirements of
    paragraph (a)(2)(i), (a)(2)(ii), or (a)(2)(iii) ... as applicable' —
    these are alternative ways to satisfy one standard, not a stacked list
    of required items, so each is correctly its own Control rather than
    an enhancement of a single one."""
    _, by_id = _load()
    assert "164.314(a)(2)(i)" in by_id
    assert "164.314(a)(2)(ii)" in by_id
    assert "164.314(a)(2)(iii)" in by_id


def test_special_characters_decoded_correctly():
    _, by_id = _load()
    text = by_id["164.314(a)(2)(i)"].control_statement
    assert "—" in text  # em dash, not the literal XML entity
    assert "�" not in text


def test_raises_on_missing_subpart_c():
    from policyforge.ingest.hipaa_loader import parse_hipaa_security_rule

    try:
        parse_hipaa_security_rule("<DIV5>no subpart c here</DIV5>")
    except ValueError as exc:
        assert "Subpart C" in str(exc)
    else:
        raise AssertionError("expected ValueError when Subpart C is absent")
