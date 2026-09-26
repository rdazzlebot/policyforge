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
