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


def _pull(**overrides):
    pull = {
        "number": 132,
        "title": "a change",
        "headRefName": "fix/local-provider-accounting",
        "updatedAt": _ago(600),
        "mergeStateStatus": "CLEAN",
        "isDraft": False,
        "author": {"login": "e2"},
    }
    pull.update(overrides)
    return pull


def _run(monkeypatch, pulls, pending=0, argv=None):
    monkeypatch.setattr(stale_prs, "open_pull_requests", lambda repo=None: pulls)
    monkeypatch.setattr(stale_prs, "pending_checks", lambda number, repo=None: pending)
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
