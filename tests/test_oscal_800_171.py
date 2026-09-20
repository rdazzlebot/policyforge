"""SP 800-171 rev 3 through the OSCAL loader's 800-171 dialect.

**The failure this file exists to catch is not a crash and not an empty.**
Reading 800-171 with 800-53's rules does not raise. It produces 97
well-formed controls, zero empty statements, zero empty titles, zero
unresolved parameter inserts, 17 families — and every `control_id` is a
sentence, because 800-171's unclassed `label` prop is the control's title
with the citation in brackets where 800-53's is the bare citation.

Every count check passes on that catalog. So the assertions that matter
here pin the *shape* of the identifiers, which is the only thing that
separates a right catalog from the well-formed wrong one.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from policyforge.ingest.oscal_loader import (
    CATALOG_URL,
    CATALOG_URL_800_171,
    NIST_800_53_REV5,
    NIST_800_171_REV3,
    OSCAL_REF,
    parse_oscal_catalog,
)

FIXTURE = Path(__file__).parent / "fixtures" / "oscal_800-171r3_excerpt.json"
CATALOG = Path(__file__).parent.parent / "data" / "frameworks" / "nist-800-171-r3"

#: `03.01.01` — two digits, dot, two, dot, two.
CONTROL_ID_RE = re.compile(r"^\d{2}\.\d{2}\.\d{2}$")
#: `03.01` — the family it belongs to.
FAMILY_RE = re.compile(r"^\d{2}\.\d{2}$")


@pytest.fixture(scope="module")
def source() -> dict:
    return json.loads(FIXTURE.read_bytes().decode("utf-8"))


@pytest.fixture(scope="module")
def parsed(source) -> list:
    controls, _ = parse_oscal_catalog(source, dialect=NIST_800_171_REV3)
    return controls


@pytest.fixture(scope="module")
def shipped() -> list[dict]:
    return json.loads((CATALOG / "controls.json").read_text(encoding="utf-8"))


# --------------------------------------------------------------------------
# The identifiers, which is the whole point
# --------------------------------------------------------------------------


def test_every_control_id_is_a_citation_not_a_sentence(parsed):
    """**The assertion that separates right from well-formed-wrong.**

    Under 800-53's rules these come out as `'Account Management
    (03.01.01)'` — countable, renderable, crosswalkable, and not something
    anyone would cite. A regression to `_plain_label` fails here and
    nowhere else, because every count stays correct.
    """
    assert parsed, "no controls parsed"
    wrong = [c.control_id for c in parsed if not CONTROL_ID_RE.match(c.control_id)]

    assert wrong == [], f"control ids that are not citations: {wrong}"


def test_every_family_is_a_citation_not_a_group_id(parsed):
    """`03.01`, not `SP_800_171_03.01`. 800-53's group carries a bare
    `label` prop ("AC"); 800-171's carries "Access Control (03.01)" and
    the id is the internal OSCAL one."""
    wrong = [c.family_abbr for c in parsed if not FAMILY_RE.match(c.family_abbr or "")]

    assert wrong == [], f"family abbreviations that are not citations: {wrong}"


def test_a_control_belongs_to_the_family_its_citation_names(parsed):
    """`03.01.01` is in family `03.01`. Holds the two extractors against
    each other, so a dialect that got one right and the other wrong is
    caught rather than looking consistent."""
    for control in parsed:
        assert control.control_id.startswith(control.family_abbr + ".")


def test_the_shipped_catalog_has_the_same_identifier_shapes(shipped):
    """Pinned on the artefact as well as the parse. The catalog is what
    ships; the parse is what would ship if someone re-ran the ETL."""
    assert len(shipped) == 97
    assert all(CONTROL_ID_RE.match(c["control_id"]) for c in shipped)
    assert all(FAMILY_RE.match(c["family_abbr"]) for c in shipped)


# --------------------------------------------------------------------------
# What the source does and does not contain
# --------------------------------------------------------------------------


def test_the_source_has_no_nested_controls_and_so_the_catalog_has_none(source, parsed):
    """**Derived from the document, not asserted as a bare zero.**

    800-171 rev 3 is structurally flat — no control carries nested
    controls, verified across all 130 in the full publication. So zero
    enhancements is correct. Written this way because `== 0` alone would
    also pass on the day the parser stopped seeing nesting, which is when
    a catalog silently loses every enhancement it should have had.
    """
    nested = [
        c["id"]
        for g in source["catalog"]["groups"]
        for c in g.get("controls", [])
        if c.get("controls")
    ]

    assert nested == [], f"the source now nests controls: {nested}"
    assert sum(len(c.enhancements) for c in parsed) == 0


def test_withdrawn_requirements_are_excluded_and_counted(source):
    """Same treatment as 800-53's withdrawn enhancements: dropped, and the
    tally returned so the caller can report it."""
    in_source = [
        c["id"]
        for g in source["catalog"]["groups"]
        for c in g.get("controls", [])
        if any(
            p.get("name") == "status" and p.get("value") == "withdrawn" for p in c.get("props", [])
        )
    ]
    controls, withdrawn = parse_oscal_catalog(source, dialect=NIST_800_171_REV3)

    assert in_source, "the fixture must contain withdrawn requirements to test this"
    assert withdrawn == len(in_source)
    emitted = {c.control_id for c in controls}
    assert not (emitted & {c.rsplit("_", 1)[-1] for c in in_source})


def test_no_baseline_is_claimed_because_rev_3_publishes_none(parsed):
    """A measured zero that would otherwise read as a parse failure.
    800-53 ships Low/Moderate/High profiles; rev 3 ships none, so every
    `baseline` is empty and that is the source's doing."""
    assert all(not (c.baseline or "").strip() for c in parsed)


# --------------------------------------------------------------------------
# Part labels
# --------------------------------------------------------------------------


def test_part_labels_lose_the_control_id_they_repeat(parsed):
    """`SR-03.01.01.a` renders as `a`. The reader already has the control
    id; what the label adds is the position.

    Measured lossless before it was relied on: 252 part labels across
    every live control in rev 3, 252 matching `<prefix><id>.<segment>`,
    one prefix (`SR-`), zero exceptions.
    """
    account_management = next(c for c in parsed if c.control_id == "03.01.01")

    assert account_management.control_statement.startswith("a Define the types")
    assert "SR-03.01.01" not in account_management.control_statement


def test_a_label_that_does_not_fit_the_shape_survives_untouched():
    """The part that makes stripping safe rather than assuming. If NIST
    ever puts something else in a label it stays visible instead of being
    mangled into a plausible single letter."""
    from policyforge.ingest.oscal_loader import _strip_control_id_from_label

    assert _strip_control_id_from_label("SR-03.01.01.a", "03.01.01") == "a"
    assert _strip_control_id_from_label("SR-03.01.01.c.01", "03.01.01") == "c.01"
    assert _strip_control_id_from_label("See also 03.01.02", "03.01.01") == "See also 03.01.02"
    assert _strip_control_id_from_label("NOTE", "03.01.01") == "NOTE"


def test_the_rendered_label_difference_from_800_53_is_nists_not_ours(parsed):
    """800-53 renders `a.` and 800-171 renders `a`, because 800-53's label
    prop contains the dot and 800-171's segment does not. Pinned so nobody
    "fixes" the asymmetry by adding a character NIST did not publish."""
    account_management = next(c for c in parsed if c.control_id == "03.01.01")

    assert not account_management.control_statement.startswith("a.")


# --------------------------------------------------------------------------
# The URLs, pinned as literals
# --------------------------------------------------------------------------


def test_both_catalog_urls_are_pinned_literally():
    """NIST spells the two filenames differently — note where the hyphen
    goes — so a URL built by substitution from the framework name 404s.
    Pinned as strings for the reason `test_ecfr_fetch.py` pins its own: a
    change of behaviour should fail, not a change of shape."""
    root = f"https://raw.githubusercontent.com/usnistgov/oscal-content/{OSCAL_REF}"

    assert f"{root}/nist.gov/SP800-53/rev5/json/NIST_SP-800-53_rev5_catalog.json" == CATALOG_URL
    assert (
        f"{root}/nist.gov/SP800-171/rev3/json/NIST_SP800-171_rev3_catalog.json"
        == CATALOG_URL_800_171
    )
    # NIST spells it differently *within a single URL*: the 800-53
    # directory is `SP800-53` and the file in it is `NIST_SP-800-53_...`.
    # 800-171 uses `SP800-171` in both. So neither a per-catalog template
    # nor a global one produces these; only literals do.
    assert "/SP800-53/" in CATALOG_URL
    assert "/NIST_SP-800-53_rev5_catalog.json" in CATALOG_URL
    assert "/SP800-171/" in CATALOG_URL_800_171
    assert "/NIST_SP800-171_rev3_catalog.json" in CATALOG_URL_800_171
    assert "NIST_SP-800-171" not in CATALOG_URL_800_171


def test_each_dialect_records_where_it_was_read_from(parsed):
    assert all(c.source_path == CATALOG_URL_800_171 for c in parsed)
    assert NIST_800_53_REV5.source_url == CATALOG_URL


def test_the_framework_key_is_the_one_the_crosswalk_already_knows(parsed):
    """`FRAMEWORK_ALIASES` carries ("800-171", "nist-800-171") from the
    keying work, so this catalog must not invent a different name."""
    from policyforge.mapping.crosswalk import FRAMEWORK_ALIASES

    assert {c.framework for c in parsed} == {"NIST 800-171"}
    assert ("800-171", "nist-800-171") in FRAMEWORK_ALIASES


def test_the_version_carries_the_published_revision(parsed):
    assert {c.framework_version for c in parsed} == {"Rev 3 (1.1.0)"}
