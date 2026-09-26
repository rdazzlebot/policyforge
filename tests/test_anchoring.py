"""One parent/child rule for every caller (#377).

The rule was written at least seven times, and each copy broke on its own
(#312, #318, #335, #339, #345, #369). These tests hold the one copy to what
each broken one got wrong, and hold every other module to not writing an
eighth.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from policyforge.mapping.crosswalk import TOPIC_ANCHORS
from policyforge.topics import anchoring
from policyforge.topics.anchoring import anchor_keys, parent_of

SRC = Path(__file__).resolve().parent.parent / "src" / "policyforge"


def test_every_catalog_a_topic_may_anchor_has_a_grammar():
    """A catalog made anchorable without a grammar would have its children
    owned by nobody, silently: `Govern 1` reported seven orphans that way."""
    assert set(anchoring._PARENT_RES) == set(TOPIC_ANCHORS)


@pytest.mark.parametrize(
    ("requirement_id", "framework", "keys"),
    [
        ("AC-2(3)", "NIST 800-53", {"AC-2(3)", "AC-2"}),
        ("AC-2", "NIST 800-53", {"AC-2"}),
        ("Govern 1.1", "NIST AI RMF", {"Govern 1.1", "Govern 1"}),
        ("Govern 1", "NIST AI RMF", {"Govern 1"}),
        # #336: the Playbook's ids read like the Core's, and a rule that read
        # no framework claimed 72 Playbook rows under an anchored category.
        ("Govern 1.1", "NIST AI RMF Playbook", set()),
        # Reached through the crosswalk, never anchored beside 800-53.
        ("AC-2(3)", "FedRAMP", set()),
        ("164.308(a)(1)", "HIPAA Security Rule", set()),
    ],
)
def test_the_ids_a_topic_may_anchor(requirement_id, framework, keys):
    assert anchor_keys(requirement_id, framework) == keys


def test_a_grammar_is_applied_only_to_its_own_catalog():
    """An 800-53 grammar applied to an AI RMF id, or the reverse, finds no
    parent: the grammar is chosen by the framework, not tried in turn."""
    assert parent_of("Govern 1.1", "NIST 800-53") is None
    assert parent_of("AC-2(1)", "NIST AI RMF") is None


# ---- discover (#345) ----


@pytest.mark.parametrize(
    ("body", "proposed"),
    [
        # The AI governance page that proposed nothing.
        ("Risk [NIST AI RMF Govern 1.1] and [NIST AI RMF Govern 1.2]", ["Govern 1"]),
        # Its 800-53 twin, unchanged.
        ("Accounts [NIST 800-53 AC-2(1)] and [NIST 800-53 AC-2]", ["AC-2"]),
        # A topic owns nothing in the Playbook.
        ("Suggested [NIST AI RMF Playbook Govern 1.1 Action 3]", []),
        # The house shorthand, and a sentence with no tag at all.
        ("[NIST AC-2] [NIST AC-6(5)]", ["AC-2", "AC-6"]),
        ("This page implements AC-2 and AC-2(3) and IA-5.", ["AC-2", "IA-5"]),
        # A catalog topics do not anchor proposes no anchor of its own.
        ("Access [HIPAA Security Rule 164.308(a)(3)(i)]", []),
    ],
)
def test_discovery_proposes_what_a_topic_would_anchor(body, proposed):
    from policyforge.zardoz.discover import _anchor_controls

    assert _anchor_controls([body]) == proposed


# ---- no caller writes its own copy ----

#: The spellings of an id grammar: a two-letter family and a dash
#: (`[A-Z]{2}-`, with or without a group between), a dotted subcategory
#: (`\d+\.\d+`), and an enhancement's parentheses (`\(\d+\)`). Matched
#: against every string literal, so a copy hidden in a regex is found.
_GRAMMAR = re.compile(r"\[A-Z(?:a-z)?\]\{2\}\)?-|\\d\+\\\.\\d\+|\\d\+\)\\\.|\\\(\\d\+\\\)")

#: `.split("(")` and its relatives: the other way to find a parent.
_SPLITS = {"split", "rsplit", "partition", "rpartition"}


def _reads_anchors(tree: ast.AST) -> bool:
    """Whether a module reads a topic's anchors, by attribute or `getattr`."""
    return any(
        (isinstance(node, ast.Attribute) and node.attr == "nist_controls")
        or (isinstance(node, ast.Constant) and node.value == "nist_controls")
        for node in ast.walk(tree)
    )


def _anchor_readers() -> dict[str, ast.AST]:
    """Every module that reads a topic's anchors: the population, derived
    from the code rather than listed, so a new reader joins it unasked."""
    readers = {}
    for path in sorted(SRC.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        if path.name != "anchoring.py" and _reads_anchors(tree):
            readers[path.relative_to(SRC).as_posix()] = tree
    return readers


def _copies(tree: ast.AST) -> list[str]:
    found = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in _SPLITS
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and node.args[0].value in {"(", "."}
        ):
            found.append(f"line {node.lineno}: .{node.func.attr}({node.args[0].value!r})")
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and _GRAMMAR.search(node.value)
        ):
            found.append(f"line {node.lineno}: id grammar {node.value[:50]!r}")
    return found


def test_the_population_is_not_empty_and_holds_the_known_callers():
    """The scan's own extent, checked against the callers #377 names: a
    scan that found no readers would pass the test below by finding nothing."""
    readers = set(_anchor_readers())
    for module in (
        "topics/coverage.py",
        "topics/bundles.py",
        "topics/satisfies.py",
        "frameworks/drift.py",
        "zardoz/discover.py",
        "cli/programme.py",
    ):
        assert module in readers, module


def test_no_module_that_reads_anchors_writes_its_own_parent_rule():
    """Every copy found so far lived in a module that reads `nist_controls`,
    and each spelled the grammar itself. Only `topics/anchoring.py` may."""
    offenders = {
        module: copies for module, tree in _anchor_readers().items() if (copies := _copies(tree))
    }
    assert offenders == {}, (
        "These modules read a topic's anchors and spell an id grammar or split "
        "an id themselves; use policyforge.topics.anchoring instead:\n"
        + "\n".join(f"  {m}: {c}" for m, c in sorted(offenders.items()))
    )


# ---- document reach: the broader breadth (80's ruling on #377) ----


def _docs(tmp_path, **bodies):
    root = tmp_path / "docs" / "standards"
    root.mkdir(parents=True)
    for name, body in bodies.items():
        (root / f"{name}.md").write_text(f"# {name}\n\n{body}\n", encoding="utf-8")
    return tmp_path / "docs"


CORE = {"Govern 1", "Govern 1.3", "Govern 1.5", "Govern 2", "Govern 2.1"}
PLAYBOOK = {"Govern 1.1", "Govern 1.1 Action 3", "Govern 1.1 Action 5", "Govern 1.2 Action 1"}


def test_an_ai_rmf_change_reaches_every_document_in_its_category(tmp_path):
    """Before #377 no AI RMF change reached any document: the recogniser knew
    only 800-53 shapes. Now `Govern 1.3` reaches `Govern 1` and `Govern 1.x`."""
    from policyforge.frameworks.drift import documents_citing

    root = _docs(
        tmp_path,
        exact="Documented. [NIST AI RMF Govern 1.3]",
        category="Governed. [NIST AI RMF Govern 1]",
        sibling="Inventoried. [NIST AI RMF Govern 1.5]",
        other="Trained. [NIST AI RMF Govern 2.1]",
        playbook="NIST suggests it. [NIST AI RMF Playbook Govern 1.1 Action 3]",
    )
    hits = documents_citing({"Govern 1.3"}, root, framework="NIST AI RMF", catalog_ids=CORE)
    assert hits == {
        "Govern 1.3": ["standards/category.md", "standards/exact.md", "standards/sibling.md"]
    }


def test_a_playbook_change_reaches_only_playbook_citations_of_its_subcategory(tmp_path):
    from policyforge.frameworks.drift import documents_citing

    root = _docs(
        tmp_path,
        same="NIST suggests it. [NIST AI RMF Playbook Govern 1.1 Action 5]",
        other="NIST suggests it. [NIST AI RMF Playbook Govern 1.2 Action 1]",
        core="Documented. [NIST AI RMF Govern 1.1]",
    )
    hits = documents_citing(
        {"Govern 1.1 Action 3"}, root, framework="NIST AI RMF Playbook", catalog_ids=PLAYBOOK
    )
    assert hits == {"Govern 1.1 Action 3": ["standards/same.md"]}


def test_an_800_53_change_reaches_its_siblings_and_the_shorthand(tmp_path):
    """Sibling reach stays, now by rule; `[NIST AC-2(3)]` resolves to 800-53
    because it is the catalog being diffed."""
    from policyforge.frameworks.drift import documents_citing

    root = _docs(
        tmp_path,
        sibling="Reviewed. [NIST AC-2(3)]",
        full="Reviewed. [NIST 800-53 AC-2]",
        other="Backed up. [NIST CP-9]",
    )
    hits = documents_citing(
        {"AC-2(1)"}, root, framework="NIST 800-53", catalog_ids={"AC-2", "AC-2(1)", "AC-2(3)"}
    )
    assert hits == {"AC-2(1)": ["standards/full.md", "standards/sibling.md"]}


def test_a_crosswalked_change_reaches_800_53_documents_through_its_mapping(tmp_path):
    """80's ruling on #377: FedRAMP reaches FedRAMP-cited documents, and NIST
    ones only through the crosswalk. An 800-171 change reaches 800-53
    documents in the families NIST maps it to, in full and in shorthand."""
    from policyforge.frameworks.drift import documents_citing

    root = _docs(
        tmp_path,
        own="Managed. [NIST 800-171 03.01.01]",
        mapped="Reviewed. [NIST 800-53 AC-2(5)]",
        shorthand="Reviewed. [NIST AC-2]",
        unmapped="Backed up. [NIST 800-53 CP-9]",
    )
    crosswalk = {"AC-2": {"nist-800-171": ["03.01.01"]}}
    hits = documents_citing(
        {"03.01.01"}, root, framework="NIST 800-171", catalog_ids={"03.01.01"}, crosswalk=crosswalk
    )
    assert hits == {
        "03.01.01": ["standards/mapped.md", "standards/own.md", "standards/shorthand.md"]
    }


def test_topic_keys_reach_a_crosswalked_catalog_only_through_the_loaded_crosswalk():
    from policyforge.topics.anchoring import topic_keys

    crosswalk = {"AC-2(3)": {"nist-800-171": ["03.01.01"]}, "RA-1": {"hipaa": ["164.308(a)(1)(i)"]}}
    assert topic_keys("03.01.01", "NIST 800-171", crosswalk) == {"AC-2(3)", "AC-2"}
    assert topic_keys("164.308(a)(1)(i)", "HIPAA Security Rule", crosswalk) == {"RA-1"}
    # Only what is loaded (80's condition): no crosswalk, no reach.
    assert topic_keys("03.01.01", "NIST 800-171") == set()
    # A partial relationship does not reach, by coverage's one reading (#185).
    partial = {("nist-800-171", "03.01.01", "AC-2(3)"): "superset"}
    assert topic_keys("03.01.01", "NIST 800-171", crosswalk, partial) == set()
