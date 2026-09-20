"""`/coverage` scopes to the set the topic registry anchors to.

Handing every loaded catalog to `analyze_coverage`'s `nist_controls`
made a HIPAA or CFR requirement an orphan by construction — no topic
anchors to its identifiers — so the denominator grew with every install
while the numerator never moved. `_addresses` in the same module already
did this correctly; these hold `_coverage` to its neighbour.
"""

from __future__ import annotations

# ---- the coverage skill's zero rows -----------------------------------------


def _coverage_state():
    from pathlib import Path
    from types import SimpleNamespace

    from policyforge.topics.registry import load_topics

    root = Path(__file__).resolve().parent.parent
    return SimpleNamespace(
        topics=load_topics(root / "config" / "topics.example.yaml"),
        controls_paths=[],
        config={},
        content_dir=None,
    )


def test_a_zero_row_never_suggests_a_command_that_would_be_refused():
    """**The third instance of a pattern this project owns: the product
    instructing an action it refuses.**

    `overlay.py` told a reader to cite a catalog no tag could name. The
    same module's comment records renaming re-opening that class once
    already. Here the else-branch tells a reader to run `crosswalk seed`
    — which `seed_overlay` refuses with `NotAnchorableError` for exactly
    the catalog the if-branch is supposed to catch.

    `_refusal_reason` returning `None` is not a neutral default. It is a
    positive claim — *nobody has mapped this yet* — so a function whose
    None-branch asserts something is one rename away from asserting it
    falsely, and this is its second consumer. Found by b5.
    """
    from policyforge.crosswalk.overlay import _refusal_reason
    from policyforge.zardoz.skills import _coverage

    output = _coverage(_coverage_state(), [])
    seed_lines = [ln for ln in output.splitlines() if "crosswalk seed --framework" in ln]

    # Guard the population, or the loop below asserts nothing on an empty
    # list and this reports green. 80 caught that; it is entry 1 of the
    # checks-that-cannot-fail catalogue, in a test written about that
    # class. The test one down already guards its own rows this way.
    assert seed_lines, (
        "no zero row suggests `crosswalk seed`, so this test checked nothing. "
        "If every framework is now mapped that is good news and this guard "
        "needs rewriting rather than deleting."
    )

    for line in seed_lines:
        named = line.split("--framework", 1)[1].strip().strip("`").strip().strip("'\"")
        assert _refusal_reason(named) is None, (
            f"the report tells a reader to seed {named!r}, which seed_overlay "
            f"refuses with NotAnchorableError. That is the product instructing "
            f"an action it declines to perform."
        )


def test_the_refused_catalog_gets_the_design_note_not_the_seed_suggestion():
    """The if-branch, so the pair is covered rather than just the else."""
    from policyforge.zardoz.skills import _coverage

    output = _coverage(_coverage_state(), [])
    row = [ln for ln in output.splitlines() if "CFR-171-INFORMATION-BLOCKING:" in ln]

    assert row, "the refused catalog has no zero-row note at all"
    assert "not mapped by design" in row[0]
    assert "crosswalk seed" not in row[0]


def test_a_reason_sentence_survives_the_house_citation_spelling():
    """Neither split works; the shared boundary rule does.

    b5 found `split(".")` cutting `45 C.F.R.` to `45 C` and proposed
    `split(". ")`. That is still wrong — `C.F.R. 171` carries a
    stop-space of its own — so the fix is the regex `entail/base.py`
    already has rather than a second attempt at splitting.
    """
    from policyforge.zardoz.skills import _first_sentence

    sentence = "A practice under 45 C.F.R. 171.203(a) qualifies. Second sentence."

    assert sentence.split(".")[0] == "A practice under 45 C"
    assert sentence.split(". ")[0] == "A practice under 45 C.F.R"
    assert _first_sentence(sentence) == "A practice under 45 C.F.R. 171.203(a) qualifies."


def test_the_shell_shares_the_one_sentence_boundary_rule():
    """A second copy drifts the day someone teaches one of them an
    abbreviation. Same argument as every reader sharing SOURCE_TAG_RE."""
    import inspect

    from policyforge.zardoz.skills import _first_sentence

    assert "_BOUNDARY_RE" in inspect.getsource(_first_sentence)
