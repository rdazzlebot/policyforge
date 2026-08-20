"""Smoke test so CI has something to run. Replace/expand as real modules
land (mapping, synthesis, generate)."""


def test_package_imports():
    import policyforge  # noqa: F401


def test_markdown_quality_check(tmp_path):
    from policyforge.export.markdown_exporter import check_markdown_quality, write_markdown

    good = write_markdown(
        "# Title\n\nSome well-formed text.\n", output_dir=tmp_path, filename="good.md"
    )
    assert check_markdown_quality(good) is True

    # Sloppy formatting (extra blank lines, inconsistent bullet markers)
    # should fail the check rather than silently pass as "primary
    # deliverable quality" output.
    bad = write_markdown(
        "# Title\n\n\n\n* one\n- two\n", output_dir=tmp_path, filename="bad.md"
    )
    assert check_markdown_quality(bad) is False


def test_nist_vault_loader_parses_fixture(tmp_path):
    from policyforge.ingest.nist_vault_loader import parse_control_file

    fixture = tmp_path / "AC-2.md"
    fixture.write_text(
        """---
type: control
control_id: AC-2
family: Access Control
family_abbr: AC
title: Account Management
framework: NIST 800-53
version: Rev 5
baseline: Low, Moderate, High
status: not-implemented
priority: ""
tags: [nist, 800-53, ac, control]
---

# AC-2: Account Management

## Control Statement

> Manage information system accounts.

## Discussion

Account management covers the full lifecycle.

## Control Enhancements

| Enhancement | Title | Baseline | Description |
|-------------|-------|----------|-------------|
| **AC-2(1)** | Automated System Account Management | Moderate, High | Support automated mechanisms. |

## Related Controls

[[AC-3]], [[AC-5]]

## Cross-Framework Mappings

| Framework | Equivalent |
|-----------|----------|
| FedRAMP | AC-2 (same ID) |
| HITRUST CSF | placeholder-ref-not-real-hitrust-data |
""",
        encoding="utf-8",
    )
    # Note: the HITRUST row value above is intentionally a nonsense placeholder,
    # not a real HITRUST control reference. This test only needs to prove the
    # column gets stripped by default — it should never contain anything that
    # looks like it was pulled from an actual HITRUST/MyCSF export.

    control = parse_control_file(fixture)

    assert control.control_id == "AC-2"
    assert control.title == "Account Management"
    assert "Manage information system" in control.control_statement
    assert len(control.enhancements) == 1
    assert control.enhancements[0].enhancement_id == "AC-2(1)"
    assert control.related_controls == ["AC-3", "AC-5"]
    # FedRAMP is in the default-safe crosswalk column set...
    assert control.source_crosswalk.get("fedramp") == "AC-2 (same ID)"
    # ...HITRUST is not, by default, even though it was present in the source table.
    assert "hitrust" not in control.source_crosswalk
