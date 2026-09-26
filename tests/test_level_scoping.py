"""Scoping a per-level framework to the levels that apply (#283, 80's ruling).

A synthetic catalog only: made-up references and overlay names, no HITRUST
text or labels (80). Maturity levels are alternatives, so a reference
counts the highest statement at or below the declared level; overlays are
additive, switched on by name, and matched case-insensitively after
whitespace normalisation against the catalog's own labels. Expected sets are
written out from the ruling, not derived from the code.
"""

from __future__ import annotations

import pytest

from policyforge.ingest.schema import MATURITY, OVERLAY, Control, Requirement
from policyforge.mapping.crosswalk import normalize_framework
from policyforge.topics.coverage import (
    CoverageReport,
    LevelScope,
    _framework_coverage,
    format_report,
    level_scopes,
)

NAME = "Synthetic Levels"
KEY = normalize_framework(NAME)


def _control(ref: str, *levels: str) -> Control:
    requirements = [
        Requirement(
            requirement_id=f"{ref} {label}",
            level=label,
            statement="A synthetic statement.",
            level_kind=MATURITY if label.split()[-1].isdigit() else OVERLAY,
        )
        for label in levels
    ]
    return Control(ref, ref, NAME, "v1", requirements=requirements)


CATALOG = [
    _control("X.1", "Level 1", "Level 2", "Level 3", "Level Alpha", "Level Beta Segment"),
    _control("X.2", "Level 1", "Level Alpha"),
    _control("X.3", "Level 1", "Level 2"),
]
EVERY = {r.requirement_id for c in CATALOG for r in c.requirements}


def _coverage(scopes):
    crosswalk = {"AC-2": {KEY: sorted(EVERY)}}  # keyed as build_crosswalk keys it
    (result,) = _framework_coverage(
        CATALOG, crosswalk, owned={"AC-2"}, relationships={}, family_links={}, scopes=scopes
    )
    return result


def test_undeclared_counts_every_level_and_says_so():
    result = _coverage({})
    assert set(result.covered) == EVERY and result.scoping == ""
    text = format_report(CoverageReport(scope="all controls", framework_coverage=[result]))
    assert "No level scoping is declared" in text
    # And where to declare it: the part a reader acts on.
    assert "Declare yours under frameworks.scoping in config" in text


def test_the_highest_maturity_at_or_below_is_counted_and_a_lower_one_is_named():
    result = _coverage({KEY: LevelScope(maturity=2, overlays=("alpha",))})
    assert set(result.covered) == {
        "X.1 Level 2",
        "X.1 Level Alpha",
        "X.2 Level 1",  # no Level 2 statement: Level 1 stands in
        "X.2 Level Alpha",
        "X.3 Level 2",
    }
    assert set(result.stood_in) == {"X.2 Level 1"}
    text = format_report(CoverageReport(scope="all controls", framework_coverage=[result]))
    assert "at maturity Level 2" in text and "X.2 Level 1" in text
    assert "no Level 2 statement for X.2" in text


def test_an_overlay_matches_case_and_whitespace_insensitively():
    result = _coverage({KEY: LevelScope(overlays=("  beta   SEGMENT ",))})
    maturity = {
        r.requirement_id for c in CATALOG for r in c.requirements if r.level_kind == MATURITY
    }
    assert set(result.covered) == maturity | {"X.1 Level Beta Segment"}


def test_an_unknown_overlay_is_refused_naming_the_nearest_labels():
    with pytest.raises(ValueError, match=r"'Alpah' is not a level.*nearest: 'Level Alpha'"):
        _coverage({KEY: LevelScope(maturity=1, overlays=("Alpah",))})


def test_scoping_is_read_from_config_and_a_bad_maturity_is_refused():
    config = {"frameworks": {"scoping": {NAME: {"maturity": 2, "overlays": ["Alpha"]}}}}
    assert level_scopes(config) == {KEY: LevelScope(maturity=2, overlays=("Alpha",))}
    for bad in ("two", 0, True):
        with pytest.raises(ValueError, match="must be a level number"):
            level_scopes({"frameworks": {"scoping": {NAME: {"maturity": bad}}}})


def _hitrust_catalog():
    """Built under the framework name the real HITRUST importer writes, which
    the tests above never used: they built the catalog and the config key
    from one constant, so a mismatch between them could not show (1d on
    #461). The config keys below are written by hand."""
    from policyforge.ingest.hitrust import FRAMEWORK

    requirements = [
        Requirement("R.1 Level 1", "Level 1", "A synthetic statement.", MATURITY),
        Requirement("R.1 Level 2", "Level 2", "A synthetic statement.", MATURITY),
    ]
    return [Control("R.1", "R.1", FRAMEWORK, "v1", requirements=requirements)]


def _hitrust_coverage(config_key: str):
    catalog = _hitrust_catalog()
    config = {"frameworks": {"scoping": {config_key: {"maturity": 1}}}}
    crosswalk = {"AC-2": {"hitrust-csf": ["R.1 Level 1", "R.1 Level 2"]}}
    (result,) = _framework_coverage(
        catalog, crosswalk, owned={"AC-2"}, relationships={}, family_links={},
        scopes=level_scopes(config),
    )  # fmt: skip
    return result


def test_the_key_the_importer_writes_applies():
    result = _hitrust_coverage("hitrust-csf")
    assert set(result.covered) == {"R.1 Level 1"} and result.scoping


def test_a_key_that_names_no_loaded_framework_is_refused_not_skipped():
    """`hitrust` normalises to `hitrust`, not `hitrust-csf`: the scope was
    skipped and the report said nothing was declared."""
    for key in ("hitrust", "HITRUST CSF"):
        with pytest.raises(ValueError, match=r"not a loaded per-level framework.*hitrust-csf"):
            _hitrust_coverage(key)


def test_the_documented_example_key_is_the_one_the_importer_writes():
    """The example is what a user copies. It named `hitrust`, which applied to
    nothing (1d on #461): read its commented key and resolve it."""
    import re
    from pathlib import Path

    from policyforge.ingest.hitrust import FRAMEWORK

    example = Path(__file__).resolve().parent.parent / "config" / "config.example.yaml"
    text = example.read_text(encoding="utf-8")
    block = text[text.index("  # scoping:") :]
    (key,) = re.findall(r"^  #   ([\w-]+):", block, flags=re.M)[:1]
    assert normalize_framework(key) == normalize_framework(FRAMEWORK)


# ---- through the real CLI and the shell (1d on #461) --------------------------


def _cli(tmp_path, monkeypatch, scoping: dict):
    """`policyforge coverage` on a synthetic catalog built by the real HITRUST
    importer, with `frameworks.scoping` from a real config file."""
    import dataclasses
    import json
    from pathlib import Path

    import yaml
    from click.testing import CliRunner

    from policyforge import cli as cli_mod
    from policyforge.ingest import hitrust

    base = {
        "category": "01.0 - Synthetic Category",
        "objective": "01.01 Synthetic Objective",
        "objective_statement": "To do the synthetic thing.",
        "reference": "01.a Synthetic Control",
        "specification": "The organization shall do the synthetic thing.",
        "factor_type": "Organizational",
        "statement": "The synthetic thing is documented.",
    }
    controls = hitrust.build_controls(
        [
            hitrust.Record(**base, level="Level 1", mapping="NIST SP 800-53 r5 AC-2"),
            hitrust.Record(**base, level="Level 2", mapping="NIST SP 800-53 r5 AC-3"),
        ]
    )
    catalog = tmp_path / "levels.json"
    catalog.write_text(json.dumps([dataclasses.asdict(c) for c in controls]), encoding="utf-8")
    topics = tmp_path / "topics.yaml"
    topics.write_text(
        "topics:\n  - name: access\n    owner: team-a\n    nist_controls: [AC-2, AC-3]\n"
        "    cadence: annual\n    description: d\n",
        encoding="utf-8",
    )
    config = tmp_path / "config.yaml"
    config.write_text(yaml.safe_dump({"frameworks": {"scoping": scoping}}), encoding="utf-8")
    monkeypatch.setenv("POLICYFORGE_CONFIG", str(config))
    nist = Path(__file__).resolve().parent.parent / "data/frameworks/nist-800-53-r5/controls.json"
    return CliRunner().invoke(
        cli_mod.cli,
        ["coverage", "--topics", str(topics), "--controls", str(nist), "--controls", str(catalog)],
    )


@pytest.mark.parametrize(
    ("scoping", "message"),
    [
        ({"hitrust": {"maturity": 1}}, "not a loaded per-level framework"),
        ({"hitrust-csf": {"maturity": "two"}}, "must be a level number"),
    ],
)
def test_the_cli_refuses_a_scoping_it_cannot_apply_without_a_traceback(
    tmp_path, monkeypatch, scoping, message
):
    result = _cli(tmp_path, monkeypatch, scoping)
    assert result.exit_code != 0, result.output
    assert message in result.output, result.output
    assert "Traceback" not in result.output


def test_the_cli_counts_the_declared_maturity_end_to_end(tmp_path, monkeypatch):
    result = _cli(tmp_path, monkeypatch, {"hitrust-csf": {"maturity": 1}})
    assert result.exit_code in (0, 1), result.output
    assert "at maturity Level 1" in result.output, result.output
    assert "No level scoping is declared" not in result.output


def test_the_shell_shows_a_scoping_refusal_as_a_refusal():
    """zardoz's coverage skill raises it through the shell's loop, which
    prints a refusal as its class and message and anything else with a
    traceback."""
    from policyforge.topics.coverage import ScopingError
    from policyforge.zardoz.shell import refusal_types

    assert issubclass(ScopingError, refusal_types())
