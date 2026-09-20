"""The AI RMF catalog, its parser, and the claims its README makes.

**The question each test here answers is 80's: what would this have to be
wrong about for the suite to stay green?** The catalog is 19 rows of
well-formed JSON whether or not it is the Framework, so a test that only
loads it and counts would stay green through a parser that dropped a
third of the Core.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from policyforge.content.tags import source_tags
from policyforge.ingest.ai_rmf import (
    FRAMEWORK,
    FRAMEWORK_VERSION,
    FUNCTIONS,
    AiRmfParseError,
    parse_ai_rmf,
)
from policyforge.mapping.crosswalk import normalize_framework
from policyforge.topics.satisfies import split_citation

ROOT = Path(__file__).resolve().parent.parent
CATALOG = ROOT / "data" / "frameworks" / "nist-ai-rmf"
FIXTURE = ROOT / "tests" / "fixtures" / "airc_ai_rmf_core.html"


@pytest.fixture(scope="module")
def controls() -> list[dict]:
    return json.loads((CATALOG / "controls.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def parsed():
    return parse_ai_rmf(FIXTURE.read_text(encoding="utf-8", errors="replace"))


# --- what the catalog is ------------------------------------------------


def test_the_whole_core_is_present(controls):
    """19 and 72 are the Framework's own numbers, not this parser's.

    Pinned as exact equality rather than a floor: a floor would pass a
    parser that started emitting duplicates, and `>= 19` is satisfied by
    every catalog that will ever be larger by accident.
    """
    assert len(controls) == 19
    assert sum(len(c["enhancements"]) for c in controls) == 72


def test_every_category_is_contiguous_within_its_function(controls):
    """The check that catches a partial parse.

    A catalog missing `Govern 3` is well-formed, has a plausible count,
    and is wrong. Nothing else here would notice.
    """
    for function in FUNCTIONS:
        numbers = sorted(
            int(c["control_id"].split()[1]) for c in controls if c["family"] == function
        )
        assert numbers == list(range(1, len(numbers) + 1)), (
            f"{function} categories are not contiguous: {numbers}"
        )


def test_the_catalog_is_ordered_function_major(controls):
    """Counting rows says nothing about their arrangement.

    The first version of the loader sorted on the number alone and emitted
    `Govern 1, Map 1, Measure 1, Manage 1, Govern 2, ...` — every row
    present, every count correct, an order the Framework does not have.
    All three count assertions above passed against it.
    """
    families = [c["family"] for c in controls]
    assert families == sorted(families, key=FUNCTIONS.index), (
        "the four functions are interleaved rather than grouped"
    )


def test_nothing_emitted_is_empty(controls):
    """Stated over entries rather than over the file.

    A catalog whose every title is `""` is valid JSON of the right length.
    """
    for control in controls:
        assert control["title"].strip(), f"{control['control_id']} has no title"
        for enhancement in control["enhancements"]:
            assert enhancement["description"].strip(), (
                f"{enhancement['enhancement_id']} has no text"
            )


# --- citability: the defect two shipped catalogs had --------------------


def test_every_identifier_is_citable(controls):
    """**The test `45 CFR 171` and `42 CFR Part 2` failed for months.**

    Both declared a digit-initial name, so `SOURCE_TAG_RE` never matched,
    every citation to them was prose, and `satisfies --strict` exited 0
    reporting nothing cited. Every gate stayed green throughout.

    Asserted over *every* identifier rather than a worked example: a
    sample chosen because it is well known is selected for the property
    that makes it easy to get right.
    """
    for control in controls:
        for identifier in [control["control_id"]] + [
            e["enhancement_id"] for e in control["enhancements"]
        ]:
            tag = f"[{FRAMEWORK} {identifier}]"
            assert source_tags(tag) == [tag], f"{tag} is not a legal source tag"


def test_every_citation_resolves_back_to_this_catalog(controls):
    """A legal tag is not enough — it must also split the right way.

    Resolution runs against the *full* population of declared names, which
    is where the risk lives: `NIST AI RMF` competes with `NIST 800-53` and
    `NIST 800-171`, and a shorter match would strand the identifier.
    Dropping `NIST AI RMF` from the population yields
    `("NIST", "AI RMF Govern 1.1")` — the bare-`NIST` orphan the
    NIST-family split exists to prevent — so this assertion can fail.
    """
    names = sorted(_declared_names() | {FRAMEWORK})
    identifiers = [c["control_id"] for c in controls] + [
        e["enhancement_id"] for c in controls for e in c["enhancements"]
    ]
    ids = {normalize_framework(FRAMEWORK): identifiers}
    for identifier in identifiers:
        framework, requirement, _ = split_citation(f"{FRAMEWORK} {identifier}", names, ids)
        assert (framework, requirement) == (FRAMEWORK, identifier)


def test_the_catalog_keys_to_itself_and_not_to_another_nist_catalog(controls):
    assert normalize_framework(FRAMEWORK) == "nist-ai-rmf"
    assert normalize_framework(FRAMEWORK) != normalize_framework("NIST 800-53")
    assert {c["framework"] for c in controls} == {FRAMEWORK}
    assert {c["framework_version"] for c in controls} == {FRAMEWORK_VERSION}


def _declared_names() -> set[str]:
    names = set()
    for directory in sorted((ROOT / "data" / "frameworks").iterdir()):
        controls_json = directory / "controls.json"
        if controls_json.exists():
            names.add(json.loads(controls_json.read_text(encoding="utf-8"))[0]["framework"])
    return names


# --- the parser's guards, each made to fire -----------------------------
#
# A guard nobody has seen fail is a guard nobody has tested. Each of these
# mutates the fixture in the one way the corresponding check exists to
# catch, and requires the parser to raise rather than to return something
# smaller.


def test_a_page_that_is_not_the_core_raises(parsed):
    with pytest.raises(AiRmfParseError, match=r"parser failure"):
        parse_ai_rmf("<html><body>AIRC is down for maintenance.</body></html>")


def test_a_restyle_that_drops_every_row_raises():
    """The silent-empty failure, which is why the parser keys on the
    identifier rather than on the class."""
    html = FIXTURE.read_text(encoding="utf-8", errors="replace")
    with pytest.raises(AiRmfParseError):
        parse_ai_rmf(html.replace("</th>", "</td>"))


def test_a_missing_category_raises_rather_than_shrinking():
    """Delete `Govern 6` and the result must be an error, not an 18-row
    catalog. This is the mutation that every count-based check survives."""
    html = FIXTURE.read_text(encoding="utf-8", errors="replace")
    mutated = re.sub(r'<span class="[^"]*">\s*Govern 6\s*</span>', "<span>x</span>", html)
    assert mutated != html, "the mutation did not apply; the fixture changed shape"
    with pytest.raises(AiRmfParseError, match=r"contiguous|parent"):
        parse_ai_rmf(mutated)


def test_an_unknown_function_name_raises():
    html = FIXTURE.read_text(encoding="utf-8", errors="replace")
    mutated = html.replace("Measure 1", "Meassure 1")
    assert mutated != html
    # The row simply stops matching, so this lands as a contiguity or
    # parent failure rather than as "unrecognised function" — either way
    # it must not pass silently.
    with pytest.raises(AiRmfParseError):
        parse_ai_rmf(mutated)


def test_the_fetch_refuses_a_host_that_is_not_nist():
    """The parser's safety argument rests on the host being fixed."""
    from policyforge.ingest.ai_rmf import fetch_core_html

    with pytest.raises(ValueError, match="refusing to fetch"):
        fetch_core_html("https://example.invalid/core/")


# --- the README's claims ------------------------------------------------


def test_the_readme_table_matches_the_catalog(controls):
    """Three of six catalog READMEs here carried claims not derivable from
    their own `controls.json`. This one is derived, so it cannot drift.

    It caught a real error on its first run: the table's first draft said
    Measure 21 and Manage 14 — wrong in two cells, right in the total,
    because the cells were written to sum to a number already known to be
    correct.

    **Cells are parsed, not string-matched.** The first version asserted
    `"| Govern | 6 | 19 |" in readme` and went red the moment `mdformat`
    padded the columns to align them — a test that fails when the
    repository's own formatter runs is a test that gets deleted rather
    than fixed.
    """
    readme = (CATALOG / "README.md").read_text(encoding="utf-8")
    table: dict[str, tuple[str, str]] = {}
    for line in readme.splitlines():
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) == 3:
            table[cells[0]] = (cells[1], cells[2])

    for function in FUNCTIONS:
        categories = [c for c in controls if c["family"] == function]
        subcategories = sum(len(c["enhancements"]) for c in categories)
        assert function in table, f"README has no row for {function}"
        assert table[function] == (str(len(categories)), str(subcategories)), (
            f"README's {function} row says {table[function]}, catalog says "
            f"{(len(categories), subcategories)}"
        )

    assert table["**Total**"] == (
        f"**{len(controls)}**",
        f"**{sum(len(c['enhancements']) for c in controls)}**",
    )


def test_the_readme_states_the_outcome_caveat():
    """The one thing a reader must not miss.

    Asserted because it is the difference between this catalog and every
    other one here, and because a README edit that tidied it away would
    leave every other check green.
    """
    readme = (CATALOG / "README.md").read_text(encoding="utf-8")
    assert "states outcomes" in readme.lower()
    assert "no crosswalk" in readme.lower()


def test_the_catalog_is_public_domain_and_says_where_it_came_from():
    import yaml

    meta = yaml.safe_load((CATALOG / "framework.yaml").read_text(encoding="utf-8"))
    assert meta["licence"] == "public-domain"
    assert meta["id"] == "nist-ai-rmf"
    assert meta["source_url"].startswith("https://airc.nist.gov/")
    for key in ("source_ref", "source_url", "content_sha256", "fetched_at"):
        assert meta.get(key), f"provenance key {key} is missing or empty"


def test_the_parsed_fixture_reproduces_the_committed_catalog(parsed, controls):
    """The catalog is what the parser produces, not a file someone edited.

    Without this, a hand-edit to `controls.json` would survive every other
    test in this module — they all read the committed file.
    """
    import dataclasses

    regenerated = [dataclasses.asdict(c) for c in parsed]
    assert regenerated == controls
