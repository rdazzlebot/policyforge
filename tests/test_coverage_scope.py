"""`/coverage` scopes to the set the topic registry anchors to.

Handing every loaded catalog to `analyze_coverage`'s `nist_controls`
made a HIPAA or CFR requirement an orphan by construction — no topic
anchors to its identifiers — so the denominator grew with every install
while the numerator never moved. `_addresses` in the same module already
did this correctly; these hold `_coverage` to its neighbour.
"""

from __future__ import annotations

# ---- the coverage skill's zero rows -----------------------------------------


def _framework_argument(line: str) -> str:
    """The value of `--framework` in a printed remedy, and only that.

    **Parsed rather than split to end-of-line.** The first version read
    `line.split("--framework", 1)[1]`, which was exact while the flag was
    last on the line. When `--controls` was appended the same expression
    kept returning a string and started returning the wrong one — the
    name plus the rest of the command — so `_refusal_reason` looked up
    something that matches nothing and returned `None`, and the assertion
    below passed for a reason unrelated to what it tests.

    A test does not have to fail to stop working.
    """
    import shlex

    command = line.split("`")[1] if "`" in line else line
    tokens = shlex.split(command)
    return tokens[tokens.index("--framework") + 1]


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
        named = _framework_argument(line)
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


# ---- the remedy has to be performable, not merely well-formed ---------------


def test_the_suggested_command_names_the_catalogs_it_needs():
    """**80's finding: the printed remedy exited 1 when run.**

    `/coverage` answers from `discover()`, which finds every catalog on
    disk. The `crosswalk` CLI's own default context holds far fewer. So
    `crosswalk seed --framework 'NIST 800-171'` — copied exactly as the
    report printed it — failed with *"No catalog here declares the
    framework"*, while the same line run inside the shell worked.

    80 got exit 1, 9b got a clean run, from the same text. **Neither run
    was wrong; the disagreement between them was the finding.** A command
    that works only in the context that printed it is a remedy in the same
    sense that a check which cannot fail is a check.
    """
    import shlex
    from pathlib import Path

    from policyforge.zardoz.skills import _coverage

    root = Path(__file__).resolve().parent.parent
    output = _coverage(_coverage_state(), [])
    seed_lines = [ln for ln in output.splitlines() if "crosswalk seed --framework" in ln]
    assert seed_lines, "no zero row suggests `crosswalk seed`, so this test checked nothing."

    for line in seed_lines:
        tokens = shlex.split(line.split("`")[1])
        controls = [tokens[i + 1] for i, t in enumerate(tokens) if t == "--controls"]
        assert controls, (
            f"the remedy names no catalogs, so it is not runnable outside the "
            f"shell that printed it: {line.strip()}"
        )
        for path in controls:
            assert (root / path).is_file(), (
                f"the remedy points at {path!r}, which does not exist. A "
                f"suggestion naming a missing file is worse than one naming none."
            )


def test_the_suggested_paths_survive_a_posix_shell():
    r"""Forward slashes, because a backslash is an escape character.

    **This is the same defect as the test above, one level down, and it
    was in the fix for it.** `discover()` returns `data\frameworks\...`
    on Windows; pasted into bash the backslashes are eaten and the path
    arrives as `dataframeworks...`, exit 2. The first fix made the command
    context-independent and left it platform-dependent.

    Caught by running the printed text through a shell rather than reading
    it — **a remedy inherits the credibility of the finding that prompted
    it**, and gets looked at less hard for exactly that reason.
    """
    import shlex

    from policyforge.zardoz.skills import _coverage

    output = _coverage(_coverage_state(), [])
    for line in output.splitlines():
        if "crosswalk seed --framework" not in line:
            continue
        tokens = shlex.split(line.split("`")[1])
        for path in [tokens[i + 1] for i, t in enumerate(tokens) if t == "--controls"]:
            assert "\\" not in path, (
                f"the remedy contains a backslash path ({path!r}), which a POSIX "
                f"shell eats. Emit `Path(...).as_posix()`."
            )


def test_an_outcome_framework_is_refused_rather_than_suggested():
    """The AI RMF arrived documented as un-crosswalkable in four places —
    README, module docstring, command help, changelog — and `/coverage`
    still told the reader to run `crosswalk seed` against it.

    **Every piece of prose was right and the one line a user actually
    reads was wrong.** The `reason is None` branch does not omit a note,
    it prints the *other* one, so the row stayed well-formed and
    confidently said the opposite of the documentation. Found by running
    `/coverage` with the new catalog installed, not by reading the code.
    **The premise moved once and the test moved with it, deliberately.**
    The first version asserted the AI RMF appears as a crosswalk zero row
    carrying "not mapped by design". It stopped being true the moment the
    catalog became *anchorable*: an anchorable catalog is counted in the
    scope, not in the "reachable via the crosswalk" section, so it left
    that section entirely. The two mechanisms are mutually exclusive.

    The invariant underneath is unchanged and is what is asserted now:
    **whatever section it lands in, nothing ever tells the reader to seed
    a crosswalk for it.** Asserted over the whole report rather than one
    row, because the row is exactly the thing that moved.
    """
    from policyforge.mapping.crosswalk import anchors_a_topic
    from policyforge.zardoz.skills import _coverage

    output = _coverage(_coverage_state(), [])

    seed_lines = [ln for ln in output.splitlines() if "crosswalk seed" in ln]
    for line in seed_lines:
        assert "AI RMF" not in line, (
            "the report tells a reader to seed the AI RMF, which asserts that "
            "an 800-53 control ACHIEVES an AI RMF outcome — the one claim NIST "
            "declined to make when it split the Playbook out."
        )

    # And it is in the report at all, so the assertion above is not
    # satisfied by the catalog having quietly vanished from it.
    assert anchors_a_topic("NIST AI RMF"), (
        "the AI RMF is no longer anchorable, so this test is checking a "
        "configuration that no longer exists — rewrite it rather than delete it."
    )
    assert "NIST AI RMF" in output, (
        "the AI RMF does not appear in the coverage report at all. A catalog "
        "that is anchorable but invisible is worse than one that is neither."
    )


# ---- the shell and the CLI must answer one question one way ----------------


def test_the_shell_passes_the_relationships_the_cli_passes():
    """**Two views of one registry disagreed about the organisation's own
    reviewed decision.**

    `cli/programme.py` passes `relationships=accepted_relationships(...)`;
    the shell passed nothing. Every lookup then returned `None`, `None` is
    not in `PARTIAL_RELATIONSHIPS`, and a mapping recorded as `superset`
    or `intersects` counted as **full** coverage in the shell and
    **partial** in the CLI.

    Measured before the fix, with every HIPAA mapping recorded as
    `superset`: the shell said 65 of 74 covered, the CLI said 0.

    Asserted on the call rather than on a number, because the numbers move
    with the catalogs and the property does not: **whatever the CLI reads
    for this, the shell reads too.**
    """
    import inspect

    from policyforge.cli import programme
    from policyforge.zardoz import skills

    cli_source = inspect.getsource(programme)
    shell_source = inspect.getsource(skills._coverage)

    assert "relationships=accepted_relationships" in cli_source, (
        "the CLI no longer passes relationships; this test's premise is gone"
    )
    assert "relationships=accepted_relationships" in shell_source, (
        "the shell does not pass relationships, so a reviewed `superset` "
        "mapping counts as full coverage here and partial in the CLI"
    )


def test_a_partial_relationship_is_not_counted_as_full():
    """The behaviour underneath, so the check above is not the only guard.

    Built directly rather than through either caller: a crosswalk with one
    mapping, recorded as `superset`, must not report that requirement
    covered.
    """
    from policyforge.topics.coverage import PARTIAL_RELATIONSHIPS, analyze_coverage
    from policyforge.topics.registry import Topic

    controls = _nist_control("AC-2")
    other = _hipaa_control("164.308(a)(3)(i)")
    crosswalk = {"AC-2": {"hipaa": ["164.308(a)(3)(i)"]}}
    topics = [Topic(name="T", owner="O", nist_controls=["AC-2"])]

    assert "superset" in PARTIAL_RELATIONSHIPS

    full = analyze_coverage(
        topics, controls, other_controls=other, crosswalk=crosswalk, relationships={}
    )
    partial = analyze_coverage(
        topics,
        controls,
        other_controls=other,
        crosswalk=crosswalk,
        relationships={("hipaa", "164.308(a)(3)(i)", "AC-2"): "superset"},
    )

    covered = {f.framework: len(f.covered) for f in full.framework_coverage}
    with_rel = {f.framework: len(f.covered) for f in partial.framework_coverage}
    assert covered.get("hipaa") == 1, "the unqualified mapping should read as covered"
    assert with_rel.get("hipaa") == 0, (
        "a mapping the organisation reviewed as `superset` still reads as full coverage"
    )


def _nist_control(control_id):
    from policyforge.ingest.schema import Control

    return [
        Control(
            control_id=control_id, title="t", framework="NIST 800-53", framework_version="Rev 5"
        )
    ]


def _hipaa_control(control_id):
    from policyforge.ingest.schema import Control

    return [
        Control(
            control_id=control_id,
            title="t",
            framework="HIPAA Security Rule",
            framework_version="45 CFR 164",
        )
    ]
