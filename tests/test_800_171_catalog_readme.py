"""The 800-171 catalog's README, held to the catalog it describes.

Written with the catalog rather than after someone blocked a PR for it.
The HIPAA version of this test was written two hours after a change
falsified five statements in a file that ships in the wheel; the Part 2
version was written two hours before that and not carried across. A guard
scoped to the catalog you happen to be thinking about is the recurring
shape, so this one is written at the same time as the thing it guards.

Numbers derive from `controls.json`, so these fail when the README goes
stale and not when NIST publishes a new revision.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

CATALOG = Path(__file__).parent.parent / "data" / "frameworks" / "nist-800-171-r3"


@pytest.fixture(scope="module")
def controls() -> list[dict]:
    return json.loads((CATALOG / "controls.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def readme() -> str:
    """The README with whitespace collapsed.

    `mdformat` reflows prose, so a sentence this file matches on can be
    split across lines by a formatting pass that changed nothing else. The
    first version of these tests broke exactly that way. Matching on
    collapsed text asserts what the README *says* rather than how it
    happens to be wrapped.
    """
    return " ".join((CATALOG / "README.md").read_text(encoding="utf-8").split())


def test_the_requirement_and_family_counts_match_the_catalog(controls, readme):
    """`97 requirements across 17 families`."""
    families = {c["family_abbr"] for c in controls}
    stated = re.search(r"(\d+) requirements across (\d+) families", readme)

    assert stated, "the README no longer states its counts"
    assert int(stated.group(1)) == len(controls)
    assert int(stated.group(2)) == len(families)


def test_the_withdrawn_arithmetic_closes(readme):
    """`130 in the publication, 97 live, 33 withdrawn` — stated as a sum
    so a reader can check it rather than take three numbers on trust."""
    stated = re.search(r"(\d+) in the publication, (\d+) live, (\d+) withdrawn", readme)

    assert stated, "the README no longer states the withdrawn arithmetic"
    total, live, withdrawn = (int(g) for g in stated.groups())
    assert live + withdrawn == total


def test_the_live_count_in_the_arithmetic_is_the_catalog(controls, readme):
    """Holds the two claims against each other, so a README that is
    internally consistent and wrong about the artefact still fails."""
    stated = re.search(r"\d+ in the publication, (\d+) live, \d+ withdrawn", readme)

    assert stated
    assert int(stated.group(1)) == len(controls)


def test_the_readme_states_the_measured_label_finding(readme):
    """The strip is only safe because it was measured lossless. If the
    README stops carrying the figure, the next person has the conclusion
    without the evidence."""
    stated = re.search(r"(\d+) part labels across every live requirement, (\d+) matching", readme)

    assert stated, "the README no longer carries the label measurement"
    assert stated.group(1) == stated.group(2), "the measurement only supports the strip if all fit"


def test_the_readme_warns_that_a_bare_nist_citation_stops_resolving(readme):
    """**The upgrade consequence, and it is the one that costs a reader
    work.** Bundling a second NIST-family catalog makes `[NIST AC-2]`
    ambiguous, so documents written when 800-53 was the only one go
    unresolved on `satisfies --strict`. Measured, not assumed:

        bundled today   'NIST' -> 'nist-800-53'
        after this      'NIST' -> ''            unresolved
        'NIST 800-53'   resolves in both
    """
    assert "[NIST AC-2]" in readme
    assert "[NIST 800-53 AC-2]" in readme, "it must say what to write instead"
    assert "satisfies --strict" in readme


def test_the_readme_leads_with_the_revision_a_cmmc_reader_needs(readme):
    """A buyer adopting 800-171 is usually doing it because of CMMC, and
    should meet the revision difference here rather than in an
    assessment. So it is above "What was parsed", not in a footnote."""
    raw = (CATALOG / "README.md").read_text(encoding="utf-8")
    cmmc = raw.index("CMMC")
    parsed = raw.index("## What was parsed")

    assert cmmc < parsed, "the CMMC revision warning must come before the contents"
    assert "3.1.1" in raw and "03.01.01" in raw, "both identifier shapes must appear"


def test_the_empty_baseline_is_explained_rather_than_left_blank(controls, readme):
    """A measured zero that would otherwise read as a parse failure."""
    assert all(not (c.get("baseline") or "").strip() for c in controls)
    assert "no baselines" in readme.lower()


def test_the_readme_names_the_framework_key_the_catalog_uses(controls, readme):
    assert {c["framework"] for c in controls} == {"NIST 800-171"}
    assert "nist-800-171" in readme
