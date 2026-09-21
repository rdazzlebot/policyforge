"""Every state the verdict reader can report, made to happen on purpose.

**A reader nobody has seen mislabel a line is a reader nobody has tested**,
and this one adjudicates every other tool's verdict, so the states it can
produce are pinned individually rather than exercised in aggregate.

`ELSEWHERE` is the one that matters most and the one no live PR would show
on demand: a real commit that is not an ancestor of the head, from a review
against a pre-rebase history. It is constructed here from this repository's
own objects rather than mocked, because a mocked SHA cannot fail the way a
real one does.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import review_lines  # noqa: E402


def _git(*args: str) -> str:
    """Run git and **fail on a non-zero exit**.

    The first version of this returned `result.stdout.strip()` and dropped
    the status, which is the `cmd | tail` defect in the test file for the
    tool that adjudicates verdicts, on the same branch as the lint for that
    exact shape.

    It was not theoretical. On CI's shallow checkout `git rev-parse HEAD~3`
    **exits 128 and prints `HEAD~3` to stdout**, so the fixture's
    `assert head and ancestor and orphan` passed on a truthy error string
    and the failure surfaced three lines later as *"this clone has no
    history"* — a message that blamed the wrong thing and cost a reproduction
    to disbelieve. Found by policyforge-9b.
    """
    result = subprocess.run(["git", *args], capture_output=True, text=True, cwd=ROOT)
    if result.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(args)} exited {result.returncode}: "
            f"{(result.stderr or result.stdout).strip()}"
        )
    return result.stdout.strip()


#: `commit-tree` refuses without an identity, and `actions/checkout` sets
#: none — the second, independent reason this fixture failed in CI while
#: passing everywhere else. Two unrelated environment facts, one identical
#: symptom, which is why the old assertion blamed neither correctly.
_IDENTITY = ("-c", "user.name=policyforge-test", "-c", "user.email=test@invalid")


@pytest.fixture(scope="module")
def commits() -> dict[str, str]:
    """A head, an ancestor of it, and a commit that is an ancestor of nothing.

    **Built entirely with `commit-tree`, so it needs no clone history.** The
    first version read `HEAD` and `HEAD~3` from the repository, which works
    on a developer's clone and fails on CI's depth-1 checkout — the rule
    about running it somewhere other than where it was written, arriving in
    a test file about instruments that answer a different question than the
    one asked.

    Real objects rather than mocks, still: a mocked SHA cannot be an
    ancestor of anything, so it cannot distinguish `ELSEWHERE` from
    `FABRICATED`, which is the whole distinction being tested.
    """
    tree = _git("rev-parse", "HEAD^{tree}")
    ancestor = _git(*_IDENTITY, "commit-tree", tree, "-m", "base")
    head = _git(*_IDENTITY, "commit-tree", tree, "-p", ancestor, "-m", "child")
    # No `-p` at all: a real object that is an ancestor of nothing, which is
    # exactly ELSEWHERE. policyforge-9b's construction.
    orphan = _git(*_IDENTITY, "commit-tree", tree, "-m", "orphan")

    assert len({ancestor, head, orphan}) == 3, "the three commits must be distinct"
    assert (
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", orphan, head], cwd=ROOT, capture_output=True
        ).returncode
        != 0
    ), "the constructed orphan IS an ancestor; the fixture is not testing ELSEWHERE"
    assert (
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", ancestor, head], cwd=ROOT, capture_output=True
        ).returncode
        == 0
    ), "the constructed ancestor is NOT one; the fixture is not testing STALE"
    return {"head": head, "ancestor": ancestor, "orphan": orphan}


def _comment(sha: str, verdict: str = "approved", reviewer: str = "policyforge-xx") -> dict:
    return {
        "body": f"Some review prose.\n\nReviewed-SHA: {sha} verdict={verdict} reviewer={reviewer}"
    }


# --- the five states -----------------------------------------------------


def test_at_head(commits):
    loc = review_lines.location_of(commits["head"], commits["head"])
    assert loc.label == "AT HEAD"


def test_stale(commits):
    loc = review_lines.location_of(commits["ancestor"], commits["head"])
    assert loc.label == "STALE"


def test_fabricated():
    """A well-formed SHA naming no object. **This has happened here** — a
    short SHA padded to 40 characters by hand, in the convention its author
    had specified."""
    loc = review_lines.location_of("0" * 39 + "1", "HEAD")
    assert loc.label == "FABRICATED"
    assert not loc.resolves


def test_elsewhere(commits):
    """**The state no reader here had before #204**, and the one a naive
    tool gets wrong in the crediting direction: a real commit reviewed on a
    history this PR no longer carries."""
    loc = review_lines.location_of(commits["orphan"], commits["head"])
    assert loc.label == "ELSEWHERE"
    assert loc.resolves, "an ELSEWHERE commit is real; that is what distinguishes it"
    assert not loc.ancestor_of_head


def test_malformed_is_a_shape_not_a_location(commits):
    """Shape is asked without reference to the repository."""
    assert not review_lines.shape_of(commits["head"][:7], "approved").well_formed
    assert review_lines.shape_of(commits["head"], "approved").well_formed


# --- the defect this file exists to avoid --------------------------------


def test_a_malformed_line_still_gets_its_ancestry_asked(commits):
    """**policyforge-9b's `if`/`elif` defect, pinned.**

    Chaining shape and location meant a line failing the shape test never
    had its ancestry asked, and the tool reported *"a real review a strict
    reader would lose"* about a commit the PR had never carried. **It
    credited a review that was not there** — the understating direction,
    which nobody catches by reading output they expected to be right.

    A short SHA of an ELSEWHERE commit carries both faults, and both must
    be reported.
    """
    short = commits["orphan"][:8]
    shape = review_lines.shape_of(short, "approved")
    location = review_lines.location_of(short, commits["head"])

    assert not shape.well_formed, "MALFORMED"
    assert location.resolves, "and it resolves -- the ancestry question is answerable"
    assert location.label == "ELSEWHERE", (
        "and it is ELSEWHERE, which the chained version never asked"
    )


def test_a_short_sha_that_resolves_is_reported_as_resolving(commits):
    """`MALFORMED` must not be conflated with `FABRICATED`. A short SHA that
    resolves is a convention violation; one that does not is a fabrication,
    and the remedies differ."""
    resolves = review_lines.location_of(commits["head"][:8], commits["head"])
    does_not = review_lines.location_of("abcdef1", commits["head"])
    assert resolves.resolves and resolves.at_head
    assert not does_not.resolves


# --- parsing -------------------------------------------------------------


def test_only_the_last_non_empty_line_counts(commits):
    """A quoted verdict is indistinguishable from a given one anywhere but
    the end — **discussing a review would create one**, including retracting
    it."""
    quoted = {
        "body": (
            f"I am retracting this:\n\n"
            f"    Reviewed-SHA: {commits['head']} verdict=approved reviewer=policyforge-xx\n\n"
            f"It named the wrong commit."
        )
    }
    assert review_lines.verdict_lines([quoted]) == []


def test_a_real_verdict_at_the_end_is_found(commits):
    assert len(review_lines.verdict_lines([_comment(commits["head"])])) == 1


def test_a_short_sha_verdict_is_not_silently_skipped(commits):
    """**Requirement 2 of this convention's own spec, which its first
    reader failed.** A pattern demanding exactly 40 hex cannot report a
    MALFORMED line — it drops it, and a live short-SHA
    `changes-requested` went unreported."""
    found = review_lines.verdict_lines([_comment(commits["head"][:7], "changes-requested")])
    assert len(found) == 1, "a short-SHA verdict must be FOUND so it can be called MALFORMED"


def test_an_unknown_verdict_word_is_reported_not_dropped(commits):
    found = review_lines.verdict_lines([_comment(commits["head"], "looks-fine")])
    assert len(found) == 1
    assert not review_lines.shape_of(commits["head"], "looks-fine").verdict_known


# --- the four shapes the REAL corpus contains ----------------------------
#
# policyforge-9b scanned all 60 PRs: 24 carry verdict lines, 81 occurrences
# of the key. These four are what is actually out there, and the first
# version of this reader silently dropped two of them. They are facts about
# the corpus and could not have been reached by thinking harder about the
# format.


def test_a_pasted_terminal_ellipsis_does_not_vanish(commits):
    """**`0374a18…` on #172, twice — a display truncation marker, copied.**

    Demanding `[0-9a-f]{4,40}\\s` made this line vanish entirely, because
    the character after the hex was `…` rather than a space. A real verdict
    by a real reviewer, reported as absent. **That is the understating
    direction in the tool whose whole job is to say what was reviewed.**
    """
    body = f"Reviewed-SHA: {commits['head'][:7]}… verdict=approved reviewer=policyforge-80"
    found = review_lines.verdict_lines([{"body": body}])
    assert len(found) == 1, "the line must be FOUND before it can be called malformed"

    shape = review_lines.shape_of(found[0]["sha"], found[0]["verdict"], found[0]["reviewer"])
    assert "MALFORMED" in shape.faults
    assert any("trailing" in f for f in shape.faults), "the ellipsis must be named, not swallowed"

    # and the cleaned SHA still resolves, so the review is placeable
    assert review_lines.location_of(found[0]["sha"], commits["head"]).resolves


def test_markdown_bleeding_into_the_reviewer_is_reported(commits):
    """**`reviewer=policyforge-80**` in the corpus.** A strict
    `reviewer in SESSIONS` test rejects it and a strict pattern drops it;
    either way a real review disappears over a formatting character."""
    body = f"Reviewed-SHA: {commits['head']} verdict=approved reviewer=policyforge-80**"
    found = review_lines.verdict_lines([{"body": body}])
    assert len(found) == 1
    shape = review_lines.shape_of(found[0]["sha"], found[0]["verdict"], found[0]["reviewer"])
    assert "MALFORMED" not in shape.faults, "the SHA is fine; only the reviewer field is dirty"
    assert any("reviewer has trailing" in f for f in shape.faults)


def test_blocked_is_a_real_verdict_with_one_instance(commits):
    """`blocked` appears **once in 81 lines**. A vocabulary check that omits
    it rejects a real verdict — and a rare value is exactly the one an
    author leaves out of a hand-written list."""
    assert "blocked" in review_lines.VERDICTS
    shape = review_lines.shape_of(commits["head"], "blocked", "policyforge-9b")
    assert shape.verdict_known
    assert shape.faults == []


def test_prose_mentioning_the_key_is_not_a_verdict():
    """Six occurrences in the corpus are people *discussing* the convention."""
    prose = {"body": "and it belongs on #181: `Reviewed-SHA:` anchors a verdict to a commit"}
    assert review_lines.verdict_lines([prose]) == []


def test_a_complete_verdict_quoted_MID_LINE_is_not_credited(commits):
    """**This is the case where the `^` anchor actually does work**, and my
    first version of the test above did not reach it.

    Bare prose mentioning the key never matched anyway — the pattern
    requires `verdict=` and `reviewer=` too — so removing the anchor broke
    no test. The case that needs it is a *structurally complete* verdict
    line embedded in a sentence, which is what someone writes when
    discussing or retracting one.

    Found by mutating the anchor away and watching nothing fail. **A guard
    I had not seen fail was a guard I had not tested**, in the file whose
    subject is exactly that.
    """
    # It has to END the line but not START it, or `\\s*$` rejects it for a
    # different reason and the anchor is still untested. My second attempt
    # put trailing prose after it and passed with the anchor removed.
    embedded = {
        "body": (
            "Earlier I wrote, and am now withdrawing: "
            f"Reviewed-SHA: {commits['head']} verdict=approved reviewer=policyforge-xx"
        )
    }
    assert review_lines.verdict_lines([embedded]) == [], (
        "a verdict quoted inside a sentence is a discussion of a review, not one"
    )


def test_exact_duplicates_are_both_reported(commits, monkeypatch, capsys):
    """**Seven exact duplicates exist** — 80 posted the same
    `changes-requested` twice on #204.

    Reported in document order and both shown, because this is *the record*
    rather than a tally. A tool that deduplicated would be answering 'how
    many distinct objections' — a different question, and one nobody asked
    it. See the no-consent boundary below: the moment duplicates matter,
    something is counting toward a decision.
    """
    dupe = _comment(commits["ancestor"], "changes-requested", "policyforge-80")
    monkeypatch.setattr(review_lines, "fetch", lambda n, r: (commits["head"], [dupe, dupe], 2))
    review_lines.report(1, "x/y")
    out = capsys.readouterr().out
    # Count in the record only. The stale-block warning below also names
    # each one, which is right -- two unanswered objections are two things
    # to answer -- but it is a different section.
    record = out.split("!!")[0]
    assert record.count(commits["ancestor"][:12]) == 2, "both occurrences belong in the record"


# --- the population, which is the #228 half ------------------------------


def test_a_short_fetch_refuses_rather_than_reports(commits, monkeypatch, capsys):
    """**#228, inside the instrument that adjudicates every other instrument.**

    A reader that fetches 3 of 8 comments and reports those 3 cleanly is
    this week's dominant failure in the worst possible place. The second
    derivation is GitHub's own comment count, which is independent in
    dimension: server-side metadata against a paginated client fetch.
    """
    monkeypatch.setattr(
        review_lines, "fetch", lambda n, r: (commits["head"], [_comment(commits["head"])], 8)
    )
    assert review_lines.report(1, "x/y") == 2
    assert "POPULATION SHORT" in capsys.readouterr().err


def test_an_agreeing_population_proceeds(commits, monkeypatch, capsys):
    """What it must ALLOW. A guard that refuses every fetch is useless."""
    monkeypatch.setattr(
        review_lines, "fetch", lambda n, r: (commits["head"], [_comment(commits["head"])], 1)
    )
    assert review_lines.report(1, "x/y") == 0
    assert "AT HEAD" in capsys.readouterr().out


# --- stale blocks --------------------------------------------------------


def test_a_stale_block_is_warned_about(commits, monkeypatch, capsys):
    """An expiring approval is safe; an expiring block is not. A push about
    something else does not answer an objection."""
    comments = [
        _comment(commits["ancestor"], "changes-requested", "policyforge-9b"),
        _comment(commits["head"], "approved", "policyforge-80"),
    ]
    monkeypatch.setattr(review_lines, "fetch", lambda n, r: (commits["head"], comments, 2))
    review_lines.report(1, "x/y")
    out = capsys.readouterr().out
    assert "STALE BLOCK" in out
    assert "policyforge-9b" in out


def test_a_block_the_same_reviewer_later_cleared_is_not_warned_about(commits, monkeypatch, capsys):
    """**What it must NOT do.** A warning that fires on resolved objections
    trains the reader to ignore it, which costs more than the warning saves.
    """
    comments = [
        _comment(commits["ancestor"], "changes-requested", "policyforge-9b"),
        _comment(commits["head"], "approved", "policyforge-9b"),
    ]
    monkeypatch.setattr(review_lines, "fetch", lambda n, r: (commits["head"], comments, 2))
    review_lines.report(1, "x/y")
    assert "STALE BLOCK" not in capsys.readouterr().out


def test_no_verdicts_is_not_reported_as_no_objection(commits, monkeypatch, capsys):
    """'Nobody has posted one' and 'no objection stands' are different facts
    and a reader cannot tell them apart. Saying so is the whole job."""
    monkeypatch.setattr(review_lines, "fetch", lambda n, r: (commits["head"], [], 0))
    review_lines.report(1, "x/y")
    assert "NOT 'no" in capsys.readouterr().out


# --- the line it must not cross ------------------------------------------


def test_it_does_not_compute_consent():
    """Counting verdicts into a merge decision would turn a written
    convention into an authorisation mechanism, and no such mechanism
    exists here — branch protection does not distinguish these sessions
    from the user.

    Asserted over the source because it is a design boundary, not a
    behaviour: the moment a caller can ask this tool 'may I merge', the
    convention has been promoted to a control it cannot be.
    """
    source = (ROOT / "scripts" / "review_lines.py").read_text(encoding="utf-8")
    code = "\n".join(
        line for line in source.splitlines() if not line.strip().startswith(("#", '"', "*"))
    )
    for forbidden in ("is_approved", "may_merge", "can_merge", "sys.exit(1) if"):
        assert forbidden not in code, f"{forbidden!r} turns a report into an authorisation"
