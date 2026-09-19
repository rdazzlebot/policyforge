**Nothing user-facing.** `scripts/stale_prs.py` reports pull requests that
are ready to merge and have not been — `CLEAN`, no pending checks, and
untouched past a threshold. It exists because a pull request sat ready for
ten hours while being described in status reports as "other sessions'
work", which is a fact about whose branch it is rather than whose turn.
