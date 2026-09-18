"""A framework source tag is recognised by its shape, in one place.

Four readers protect, report, reach through and classify by these tags,
and each carried its own hand-written list of framework names. The bundled
starter set writes `[ARC PE-1 ...]` where the lists said `ARC-AMPE`, so
twenty-two tags were invisible to all four at once. `content/tags.py` now
decides the shape, and every reader takes it from there.

Held here: the shape on every tag form the tests and documents use; the
prose brackets the old lists matched by accident; that each reader sees a
bare-`ARC` tag; and that no reader can quietly grow its own copy again.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from policyforge.content.tags import (
    SOURCE_TAG_RE,
    framework_name,
    source_tags,
)

ROOT = Path(__file__).resolve().parents[1]

# ---- the shape ------------------------------------------------------------

TAGS = [
    "[NIST AC-2]",
    "[NIST AC-2(3)]",
    "[NIST AC-2 | HIPAA 164.308(a)(3)(i)]",
    "[NIST AC-2 \\| HIPAA 164.308]",
    "[NIST AC-2 Low/Moderate/High]",
    "[HIPAA 164.312(b)]",
    "[HITRUST 01.a]",
    "[HITRUST 01.a Level 1]",
    "[GovRAMP IA-5 | FedRAMP IA-5]",
    "[ARC-AMPE PE-1]",
    "[ARC PE-1 | NIST PE-1]",
    "[NIST 800-53 IR-1]",
    "[HIPAA Security Rule 164.308(a)(6)(i)]",
    "[SOC2 CC6.1]",
]


@pytest.mark.parametrize("tag", TAGS)
def test_every_tag_form_in_use_is_a_tag(tag):
    assert source_tags(f"Accounts are reviewed quarterly. {tag}") == [tag]


def test_the_framework_name_is_read_as_written():
    assert framework_name("[ARC PE-1 | NIST PE-1]") == "ARC"
    assert framework_name("[HIPAA Security Rule 164.308]") == "HIPAA Security Rule"
    assert framework_name("[NIST 800-53 IR-1]") == "NIST"
    assert framework_name("[SOC2 CC6.1]") == "SOC2"
    assert framework_name("not a tag") == ""


def test_findall_returns_whole_tags_because_every_reader_relies_on_it():
    """The first cut had a named group, and `findall` returned `ARC`."""
    assert SOURCE_TAG_RE.findall("x [ARC PE-1 | NIST PE-3] y") == ["[ARC PE-1 | NIST PE-3]"]
    assert SOURCE_TAG_RE.groups == 0


NOT_TAGS = [
    "[NIST AI RMF alignment]",
    "[NIST AI Risk Management Framework]",
    "[NIST CAVP]",
    "[ARC-AMPE Volume I]",
    "[ARC-AMPE Volume II SSPP, ACA Administering Entity, v1.02]",
    "[1]",
    "[12]",
    "[[Access Review Standard]]",
    "[Access Review Standard](../standards/access-review.md)",
    "[NIST AC-2](https://example.test/ac-2)",
    "[see section 3]",
    "[todo 2024]",
]


@pytest.mark.parametrize("text", NOT_TAGS)
def test_prose_links_and_footnotes_are_not_tags(text):
    assert source_tags(f"Some prose. {text} More prose.") == []


def test_tags_come_back_in_order_and_as_written():
    text = "One. [NIST AC-2] Two. [ARC PE-1 | HIPAA 164.308(a)] Three. [NIST AC-2]"

    assert source_tags(text) == ["[NIST AC-2]", "[ARC PE-1 | HIPAA 164.308(a)]", "[NIST AC-2]"]


def test_the_shape_matches_nothing_new_in_the_repository_and_drops_only_prose():
    """Measured, not assumed: over every document and catalog in the tree,
    the shape recognises every tag the old list recognised and rejects
    only brackets that were never citations."""
    import re

    old = re.compile(r"\[(?:NIST|HIPAA|FedRAMP|HITRUST|GovRAMP|ARC-AMPE)\s[^\]]*\]")
    gained: set[str] = set()
    dropped: set[str] = set()
    for path in [*ROOT.joinpath("docs").rglob("*.md"), *ROOT.joinpath("data").rglob("*")]:
        if not path.is_file() or path.suffix not in {".md", ".json", ".yaml"}:
            continue
        text = path.read_text(encoding="utf-8")
        before, after = set(old.findall(text)), set(source_tags(text))
        gained |= after - before
        dropped |= before - after

    assert gained == set()
    assert all(not any(ch.isdigit() for ch in tag.split()[1:2][0]) for tag in dropped), (
        f"dropped a bracket whose second token carries a digit: {dropped}"
    )


def test_a_placeholder_that_opens_with_a_framework_name_is_not_a_tag():
    """`[HIPAA Documentation Review Frequency]` sits mid-sentence beside
    `[Ticketing System]` and stands in for a value nobody has decided; the
    step it sits in is cited by its heading. Two reviewers read it as the
    corpus's least followable citation, and the old list counted it as one.
    The identifier rule is what tells a placeholder from a citation, and
    backticks are not: some real tags in generated documents carry them."""
    step = (
        "### Maintain HIPAA documentation in written form [HIPAA 164.316(b)(1) | "
        "HIPAA 164.316(b)(2)(ii) Required]\n\n"
        "1. Review the documentation periodically `[HIPAA Documentation Review "
        "Frequency]` and file it in the `[Contract Repository]`.\n"
        "1. Scan endpoints. `[NIST SI-3 Low | NIST SI-3 High]`\n"
    )

    assert source_tags(step) == [
        "[HIPAA 164.316(b)(1) | HIPAA 164.316(b)(2)(ii) Required]",
        "[NIST SI-3 Low | NIST SI-3 High]",
    ]


def test_a_tag_inside_a_wikilink_is_not_a_tag():
    assert source_tags("[[NIST AC-2]] but [NIST AC-2] is") == ["[NIST AC-2]"]


# ---- one shape, every reader ----------------------------------------------


def test_every_reader_uses_the_one_shape():
    """A reader that grows its own copy drifts the day a new name appears."""
    from policyforge.content import deontic
    from policyforge.edit import apply
    from policyforge.frameworks import drift

    assert apply._SOURCE_TAG_RE is SOURCE_TAG_RE
    assert drift._SOURCE_TAG_RE is SOURCE_TAG_RE
    assert deontic._CITATION_RE is SOURCE_TAG_RE


def test_the_edit_path_refuses_a_revision_that_drops_a_bare_arc_tag():
    from policyforge.edit.apply import check_edit
    from policyforge.edit.plan import EditPlan

    original = "# Physical Access\n\nBadges must be returned on exit. [ARC PE-1 | NIST PE-3]\n"
    revised = "# Physical Access\n\nBadges must be returned on exit.\n"

    check = check_edit(original, revised, plan=EditPlan(page_title="P", instruction=""))

    assert check.dropped_source_tags == ["[ARC PE-1 | NIST PE-3]"]


def test_check_reports_a_bare_arc_tag_the_document_lost(tmp_path):
    from policyforge.content.check import check_tree

    synthesis = tmp_path / "synthesis"
    synthesis.mkdir()
    (synthesis / "physical.md").write_text(
        "- Badges are returned on exit. [ARC PE-1]\n", encoding="utf-8"
    )
    docs = tmp_path / "standards"
    docs.mkdir()
    (docs / "physical.md").write_text(
        "---\ntitle: Physical\nowner: Facilities\n---\n\n# Physical\n\nBadges are returned.\n",
        encoding="utf-8",
    )

    report = check_tree(tmp_path, synthesis_dir=synthesis)

    assert any("[ARC PE-1]" in f.message for f in report.warnings)


def test_drift_reaches_a_document_that_cites_through_a_bare_arc_tag(tmp_path):
    from policyforge.frameworks.drift import documents_citing

    docs = tmp_path / "standards"
    docs.mkdir()
    (docs / "physical.md").write_text(
        "---\ntitle: Physical\n---\n\n# Physical\n\nVisitors sign in. [ARC PE-1 | NIST PE-3]\n",
        encoding="utf-8",
    )

    hits = documents_citing({"PE-3"}, tmp_path)

    assert hits == {"PE-3": ["standards/physical.md"]}


def test_deontic_counts_a_sentence_with_a_bare_arc_tag_as_cited():
    from policyforge.content.deontic import analyze

    statements = analyze("Visitors must sign in. [ARC PE-1]\n\nVisitors may bring guests.")

    assert [(s.cited, s.text) for s in statements] == [
        (True, "Visitors must sign in."),
        (False, "Visitors may bring guests."),
    ]
