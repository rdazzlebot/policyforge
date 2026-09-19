"""The shipped 42 CFR Part 2 catalog, and the README that explains it.

Provenance — that `content_sha256` still matches `controls.json` — is
covered generically for every bundled catalog by `test_provenance.py`.
What is not covered generically is the thing this catalog is unusual for:
**its README makes numeric claims about the data beside it**, and it makes
them because the count is the first thing a reader will doubt. A README
that drifts from its own catalog is worse than one that says nothing,
because it is the document that exists to stop someone re-running the
parser.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

CATALOG = Path(__file__).parent.parent / "data" / "frameworks" / "cfr-42-part-2-sud-records"


@pytest.fixture(scope="module")
def controls() -> list[dict]:
    return json.loads((CATALOG / "controls.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def readme() -> str:
    return (CATALOG / "README.md").read_text(encoding="utf-8")


def test_the_shipped_catalog_is_the_two_security_sections(controls):
    """A regenerated catalog that quietly gained entries would mean the
    conduct/control test had stopped being applied. Pinned here as well as
    in the loader, because this is the file that actually ships."""
    assert [c["control_id"] for c in controls] == ["2.16", "2.19"]
    assert [c["framework"] for c in controls] == ["42 CFR Part 2"] * 2


def test_every_shipped_requirement_has_a_distinct_citation(controls):
    """Two obligations answering to one citation is well-formed, plausible,
    and wrong only to a reader who follows the citation — which is the
    reader this catalog exists for."""
    ids = [e["enhancement_id"] for c in controls for e in c["enhancements"]]

    assert ids == sorted(set(ids), key=ids.index), f"duplicate citation in {ids}"
    assert set(ids) == {"2.16(a)", "2.16(b)", "2.19(a)", "2.19(b)"}


def test_nothing_shipped_is_empty(controls):
    """80's ruling, checked on the artefact rather than on the parser."""
    for control in controls:
        assert control["title"].strip()
        for requirement in control["enhancements"]:
            assert requirement["description"].strip(), requirement["enhancement_id"]
            assert "[Reserved]" not in requirement["description"]


def test_the_readme_count_matches_the_catalog_it_describes(controls, readme):
    """The README says "2 sections carrying 4 requirements". If the
    regulation gains a security section and someone regenerates, that
    sentence becomes false while every other check still passes."""
    requirements = sum(len(c["enhancements"]) for c in controls)
    stated = re.search(r"(\d+) sections carrying (\d+) requirements", readme)

    assert stated, "the README no longer states the count it is supposed to state"
    assert int(stated.group(1)) == len(controls)
    assert int(stated.group(2)) == requirements


def test_the_readme_names_every_control_it_ships(controls, readme):
    for control in controls:
        assert f"`{control['control_id']}`" in readme, control["control_id"]


def test_the_readme_names_what_it_rejected(readme):
    """A maintainer who sees only what was kept cannot tell thinness from
    nobody having looked. § 2.52 is the one a sceptical assessor asks
    about — it mentions sanitization and is still not a control — so it
    must be named, not just the easy § 2.66 court-order case."""
    for rejected in ("`2.52`", "`2.53`", "`2.66`"):
        assert rejected in readme, rejected

    assert "false positive" in readme, (
        "the README must keep the one term the mechanical test got wrong; "
        "a test presented as decisive is the failure this catalog avoids"
    )


def test_the_catalog_is_not_marked_unmappable():
    """Unlike 45 CFR 171, these are safeguards to implement, so `crosswalk
    seed` must treat it like any other catalog."""
    from policyforge.crosswalk.overlay import NOT_CROSSWALK_ANCHORABLE

    assert "42 CFR Part 2" not in NOT_CROSSWALK_ANCHORABLE
