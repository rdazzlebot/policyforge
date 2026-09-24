"""The queue check fires on the state that produced the ten hours, and on no other.

Written against the incident rather than against the idea of one: on
2026-09-19 a pull request sat `CLEAN` with zero pending checks for ten
hours while being listed in status reports as "other sessions' work" — a
fact about whose branch it is, read as a fact about whose turn it is.

The risk in a check like this is not missing that case. It is firing on the
four states that look similar and are someone's turn — checks running,
review outstanding, a conflict, a draft. A queue check that nags is one
people stop reading, and then the queue has no owner again with a script
running over it.
"""

from __future__ import annotations

import contextlib
import io
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import stale_prs


def _ago(minutes: int) -> str:
    moment = datetime.now(timezone.utc) - timedelta(minutes=minutes)
    return moment.isoformat().replace("+00:00", "Z")


HEAD = "a" * 40


def _verdict(sha: str = HEAD, verdict: str = "approved") -> dict:
    return {"body": f"Read it.\n\nReviewed-SHA: {sha} verdict={verdict} reviewer=policyforge-9b"}


def _pull(**overrides):
    pull = {
        "number": 132,
        "title": "a change",
        "headRefName": "fix/local-provider-accounting",
        "updatedAt": _ago(600),
        "mergeStateStatus": "CLEAN",
        "isDraft": False,
        "author": {"login": "e2"},
        "createdAt": _ago(700),
        "headRefOid": HEAD,
        # Read at head by default, so the ready-and-unmerged tests below
        # exercise only what they were written for.
        "comments": [_verdict()],
    }
    pull.update(overrides)
    return pull


def _run(monkeypatch, pulls, pending=0, argv=None, parked=()):
    monkeypatch.setattr(stale_prs, "open_pull_requests", lambda repo=None: pulls)
    monkeypatch.setattr(stale_prs, "pending_checks", lambda number, repo=None: pending)
    monkeypatch.setattr(stale_prs, "branches_without_pull_request", lambda repo=None: list(parked))
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = stale_prs.main(argv or [])
    return code, out.getvalue()


def test_the_incident_fires(monkeypatch):
    """`CLEAN`, nothing pending, ten hours: the machine is finished and a
    person has not acted. This is the only state that means that."""
    code, output = _run(monkeypatch, [_pull()])

    assert code == 1
    assert "#132" in output
    assert "10h 00m" in output


def test_it_names_the_branch_and_the_wait_rather_than_a_count(monkeypatch):
    """A count is a nag; a name and a duration are a worklist."""
    _, output = _run(monkeypatch, [_pull()])

    assert "fix/local-provider-accounting" in output
    assert "ready and untouched for 10h 00m" in output
    assert "author e2" in output


@pytest.mark.parametrize(
    "overrides, pending, why",
    [
        ({"updatedAt": _ago(20)}, 0, "ready, but not for long enough"),
        ({}, 3, "checks still running"),
        ({"mergeStateStatus": "UNSTABLE"}, 0, "checks not green"),
        ({"mergeStateStatus": "DIRTY"}, 0, "conflicting"),
        ({"mergeStateStatus": "BLOCKED"}, 0, "review outstanding"),
        ({"isDraft": True}, 0, "draft"),
    ],
)
def test_someone_elses_turn_does_not_fire(monkeypatch, overrides, pending, why):
    """Each of these is a state where the queue is working.

    Firing on them is how a check becomes a nag, and a nag is how the queue
    ends up unowned again with a script running over it.
    """
    code, _ = _run(monkeypatch, [_pull(**overrides)], pending=pending)

    assert code == 0, why


def test_a_clean_run_still_says_what_it_examined(monkeypatch):
    """A check that only speaks when it fails cannot be told apart from one
    that did not run — the defect #112 fixed in the gate."""
    code, output = _run(monkeypatch, [])

    assert code == 0
    assert "0 open pull request(s)" in output
    assert "Nothing ready has been waiting" in output


def test_not_knowing_is_a_failure_rather_than_a_pass(monkeypatch):
    """If the queue cannot be read, the question is unanswered.

    Same rule as the release check: "I could not find out" is not "nothing
    is waiting", and going quiet exactly when it cannot answer is what this
    file exists to prevent.
    """

    def boom(repo=None):
        raise RuntimeError("gh exploded")

    monkeypatch.setattr(stale_prs, "open_pull_requests", boom)
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = stale_prs.main([])

    assert code == 1
    assert "Cannot tell whether anything is waiting" in out.getvalue()


def test_the_threshold_is_a_number_a_caller_can_move(monkeypatch):
    """Ten hours passed a sixty-minute bar; it also has to pass a stricter
    one, or the default is doing all the work and the flag is decoration."""
    code, _ = _run(monkeypatch, [_pull(updatedAt=_ago(90))], argv=["--minutes", "30"])
    assert code == 1

    code, _ = _run(monkeypatch, [_pull(updatedAt=_ago(90))], argv=["--minutes", "240"])
    assert code == 0


def test_durations_are_written_for_a_reader(monkeypatch):
    """`552` is a number someone has to convert before they can care."""
    assert stale_prs.describe(45) == "45m"
    assert stale_prs.describe(600) == "10h 00m"
    assert stale_prs.describe(92) == "1h 32m"


# ---- #178: the step before ready -- a pull request nobody has read ------------


def test_an_open_pull_request_with_no_verdict_line_is_unread(monkeypatch):
    """**#161's shape.** Open, not a draft, no Reviewed-SHA line, and waiting
    past the threshold: a worklist item, and the run fails."""
    code, out = _run(monkeypatch, [_pull(mergeStateStatus="BLOCKED", comments=[])])
    assert code == 1
    assert "#132 fix/local-provider-accounting — unread for 10h 00m" in out


def test_a_verdict_on_an_older_commit_is_not_a_reading_of_this_head(monkeypatch):
    """An approval does not survive a new commit, so a verdict on another SHA
    leaves the current head unread."""
    code, out = _run(
        monkeypatch, [_pull(mergeStateStatus="BLOCKED", comments=[_verdict("b" * 40)])]
    )
    assert code == 1
    assert "read, not at head for" in out


@pytest.mark.parametrize(
    ("overrides", "why"),
    [
        ({"comments": [_verdict()]}, "read at head"),
        ({"comments": [], "updatedAt": _ago(10)}, "changed within the threshold"),
        ({"comments": [], "isDraft": True}, "a draft"),
        ({"comments": [_verdict(HEAD[:7])]}, "a 7-character prefix of head"),
        ({"comments": [_verdict(HEAD + "**")]}, "trailing formatting is cleaned"),
    ],
)
def test_the_quiet_twins_of_unread(monkeypatch, overrides, why):
    code, out = _run(monkeypatch, [_pull(mergeStateStatus="BLOCKED", **overrides)])
    assert "waiting on a reader" not in out, why
    assert code == 0, why


def test_a_six_character_prefix_is_too_short_to_count_as_at_head(monkeypatch):
    """The boundary, from the other side of `_MIN_PREFIX`."""
    _, out = _run(monkeypatch, [_pull(mergeStateStatus="BLOCKED", comments=[_verdict(HEAD[:6])])])
    assert "read, not at head" in out


def test_a_verdict_quoted_mid_comment_is_not_a_reading(monkeypatch):
    """Read with the verdict reader's own parser: only the LAST non-empty line
    of a comment is a verdict, so discussing one does not create one."""
    quoted = {"body": f"Reviewed-SHA: {HEAD} verdict=approved reviewer=policyforge-9b\n\nnot yet"}
    code, out = _run(monkeypatch, [_pull(mergeStateStatus="BLOCKED", comments=[quoted])])
    assert code == 1 and "unread" in out


def test_it_reads_verdicts_with_the_verdict_readers_parser():
    """One instrument, not two: no second Reviewed-SHA pattern in this file."""
    source = (Path(stale_prs.__file__)).read_text(encoding="utf-8")
    assert "review_lines.verdict_lines" in source
    assert r"Reviewed-SHA:\s" not in source and "re.compile" not in source


# ---- #178: pushed branches with no pull request -------------------------------


def test_a_parked_branch_is_shown_and_does_not_fail(monkeypatch):
    """Parking finished work on the remote without a PR is allowed, so it is
    reported by name and never fails the run."""
    code, out = _run(monkeypatch, [], parked=["salvage/onc-170-315-roman-numeral"])
    assert code == 0
    assert "1 pushed branch(es) with no pull request" in out
    assert "salvage/onc-170-315-roman-numeral" in out


def test_no_parked_branch_says_so(monkeypatch):
    _, out = _run(monkeypatch, [])
    assert "No pushed branch is without a pull request." in out


def test_a_failed_branch_listing_is_said_and_gates_nothing(monkeypatch):
    def boom(repo=None):
        raise RuntimeError("rate limited")

    monkeypatch.setattr(stale_prs, "open_pull_requests", lambda repo=None: [])
    monkeypatch.setattr(stale_prs, "branches_without_pull_request", boom)
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = stale_prs.main([])
    assert code == 0
    assert "pushed-with-no-PR not checked" in out.getvalue()


def test_the_branch_listing_excludes_the_default_branch_and_every_pr_head(monkeypatch):
    """Heads of MERGED and closed pull requests count too: a kept branch whose
    work landed is not parked work."""
    import json as _json

    replies = {
        ("repo", "view"): "rdazzleman/policyforge",
        ("api", "--paginate"): _json.dumps(
            [
                [{"name": "main"}, {"name": "ba/merged"}, {"name": "salvage/x"}],
                [{"name": "1d/open"}],
            ]
        ),
    }
    replies[("api", "--paginate")] = _json.dumps(
        [
            [{"name": "main"}, {"name": "ba/merged"}, {"name": "salvage/x"}],
            [{"name": "1d/open"}, {"name": "release/1.6.1"}],
        ]
    )
    # Honours --state, so asking for only OPEN pull requests would miss the
    # merged head -- a fake that ignored the flag could not see that mistake.
    pulls_by_state = {
        "open": [{"headRefName": "1d/open", "baseRefName": "release/1.6.1"}],
        "all": [
            {"headRefName": "ba/merged", "baseRefName": "release/1.6.1"},
            {"headRefName": "1d/open", "baseRefName": "release/1.6.1"},
        ],
    }

    def fake(args):
        if args[:2] == ["repo", "view"] and "defaultBranchRef" in args:
            return "main\n"
        if args[:2] == ["pr", "list"]:
            return _json.dumps(pulls_by_state[args[args.index("--state") + 1]])
        return replies[tuple(args[:2])]

    monkeypatch.setattr(stale_prs, "_gh", fake)
    # main: the default. release/1.6.1: a base, found on the real repo's first
    # run. ba/merged: a merged head. 1d/open: an open head.
    assert stale_prs.branches_without_pull_request("rdazzleman/policyforge") == ["salvage/x"]
