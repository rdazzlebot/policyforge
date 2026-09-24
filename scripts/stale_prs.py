"""Report pull requests that are ready to merge and have not been.

On 2026-09-19 a pull request sat `CLEAN` with zero pending checks for **ten
hours**. Nothing was wrong with it. It was approved, green, and mergeable,
and the release manager — whose role is to merge anyone's pull request —
listed it in three separate status reports as "open, other sessions' work".

That phrase is a fact about whose *branch* it is. It was filed as a fact
about whose *turn* it is. The two read identically and mean opposite things.

**The failure has no artefact, which is why it needs a check rather than a
habit.** A forgotten extension point fails the first time someone uses it. A
queue nobody polls produces no signal at all: green accumulates, every check
passes, and there is nothing to be red. Every pull request that moved that
day had been handed over by name and moved within minutes; the one nobody
announced was invisible, because the queue was only ever examined when
something arrived.

So this asks the question nobody was asking — *what is ready that nobody has
picked up?* — and answers it with names and durations rather than a count, so
the output is a worklist instead of a nag.

**A draft is not stale.** Neither is one waiting on checks, on review, or on
a conflict: each of those is someone's turn and the queue is working. Only
`CLEAN` with nothing pending means *the machine has no further objection and
a person has not acted*, which is the state that produced the ten hours.

Prints what it examined either way, including on a clean run, because a
check that goes quiet when it passes is indistinguishable from one that did
not run — the defect #112 fixed in the gate, which this would otherwise
reintroduce in a new file.

THE STEP BEFORE (#178). Ready-and-unmerged is the LAST place finished work
waits. It was built at the point that last hurt, which is one step below the
next place things pile up: a pull request nobody has read. #161 sat two
hours with no comment and nobody named, while a status report called the
queue healthy because every PR was green. So two more questions:

    UNREAD           open, not a draft, and no verdict line at all -- or
                     none at the current head, because an approval does not
                     survive a new commit. Over the threshold, it fails.
    PUSHED, NO PR    a branch on the remote with no pull request of any
                     state. Reported and never failed: parking finished
                     work on the remote without a PR is a legitimate thing
                     to do, and a check that fails on it forever is one
                     people stop reading. It is shown so it is a choice
                     someone can see, not a branch nobody remembers.

Verdict lines are read with `review_lines.verdict_lines` -- the same parser
the verdict reader uses -- so the two tools cannot disagree about what a
review is. "Read" means a `Reviewed-SHA:` line exists, not that anyone was
ASKED; being asked has no artefact, and a verdict line is the nearest one.
"""

from __future__ import annotations

import argparse
import json
import subprocess  # nosec B404 - runs `gh`, the tool this repository already uses
import sys
from datetime import datetime, timezone

import review_lines

#: Ready and untouched for longer than this is worth saying out loud.
#: A number rather than a judgement: the incident ran to ten hours, and an
#: hour is long enough that a merge in progress does not trip it while being
#: short enough that a working day cannot hide one.
DEFAULT_THRESHOLD_MINUTES = 60

#: The only state that means "the machine is finished and a person is not".
READY = "CLEAN"

FIELDS = (
    "number,title,headRefName,updatedAt,mergeStateStatus,isDraft,author,"
    "createdAt,headRefOid,comments"
)

#: A SHA prefix shorter than this names too many commits to count as "at head".
_MIN_PREFIX = 7


def open_pull_requests(repo: str | None = None) -> list[dict]:
    """Every open pull request, as `gh` reports them."""
    command = ["gh", "pr", "list", "--state", "open", "--json", FIELDS, "--limit", "100"]
    if repo:
        command += ["--repo", repo]
    result = subprocess.run(  # nosec B603 - fixed argv, no shell
        command, capture_output=True, text=True, encoding="utf-8", check=False
    )
    if result.returncode != 0:
        raise RuntimeError(f"gh pr list failed: {result.stderr.strip()}")
    return json.loads(result.stdout or "[]")


def pending_checks(number: int, repo: str | None = None) -> int | None:
    """How many checks are still running, or None if that cannot be read.

    `gh pr checks` exits non-zero when any check has failed, which is not an
    error here — a failing check means the pull request is not ready, and
    that is an answer rather than a fault. So the exit status is ignored and
    the rows are read instead.
    """
    command = ["gh", "pr", "checks", str(number)]
    if repo:
        command += ["--repo", repo]
    result = subprocess.run(  # nosec B603 - fixed argv, no shell
        command, capture_output=True, text=True, encoding="utf-8", check=False
    )
    if not result.stdout.strip():
        return None
    return sum(1 for line in result.stdout.splitlines() if "\tpending\t" in line)


def read_state(pull: dict) -> str:
    """`read at head`, `read, not at head`, or `unread` -- from verdict lines.

    A verdict counts as at head when its SHA, cleaned of trailing formatting,
    is a prefix of the head of at least `_MIN_PREFIX` characters. Anything
    looser would call a review of an older commit current."""
    head = pull.get("headRefOid") or ""
    verdicts = review_lines.verdict_lines(pull.get("comments") or [])
    if not verdicts:
        return "unread"
    for verdict in verdicts:
        sha, _ = review_lines.clean(verdict["sha"])
        if len(sha) >= _MIN_PREFIX and head.startswith(sha.lower()):
            return "read at head"
    return "read, not at head"


def branches_without_pull_request(repo: str | None = None) -> list[str]:
    """Remote branches no pull request of any state was ever opened from.

    Compared by name against every PR's head, open, closed or merged, so a
    merged branch someone kept is not reported. A branch that is the BASE of
    any pull request is not parked work either -- the default branch, and an
    integration branch like a release train, which PRs are opened into and
    never from. Derived from the pull requests, not a list of names: the
    first run named `release/1.6.1` as parked, because only the default
    branch was excluded."""
    target = repo or _gh(["repo", "view", "--json", "nameWithOwner", "--jq", ".nameWithOwner"])
    target = target.strip()
    default = _gh(
        ["repo", "view", target, "--json", "defaultBranchRef", "--jq", ".defaultBranchRef.name"]
    ).strip()
    names = json.loads(
        _gh(["api", "--paginate", "--slurp", f"repos/{target}/branches?per_page=100"])
    )
    branches = {b["name"] for page in names for b in page}
    pulls = json.loads(
        _gh(
            [
                "pr",
                "list",
                "--repo",
                target,
                "--state",
                "all",
                "--limit",
                "1000",
                "--json",
                "headRefName,baseRefName",
            ]
        )
    )
    heads = {p["headRefName"] for p in pulls}
    bases = {p["baseRefName"] for p in pulls}
    return sorted(branches - heads - bases - {default})


def _gh(args: list[str]) -> str:
    result = subprocess.run(  # nosec B603 - fixed argv, no shell
        ["gh", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"gh {' '.join(args[:2])} failed: {result.stderr.strip()}")
    return result.stdout


def idle_minutes(updated_at: str, *, now: datetime | None = None) -> float:
    """Minutes since the pull request last changed."""
    moment = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
    return ((now or datetime.now(timezone.utc)) - moment).total_seconds() / 60


def describe(minutes: float) -> str:
    """`9h 12m`, because "552" is a number a reader has to convert."""
    hours, rest = divmod(int(minutes), 60)
    return f"{hours}h {rest:02d}m" if hours else f"{rest}m"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--minutes",
        type=int,
        default=DEFAULT_THRESHOLD_MINUTES,
        help=f"how long ready-and-untouched is too long (default {DEFAULT_THRESHOLD_MINUTES})",
    )
    parser.add_argument("--repo", default=None, help="owner/name, for running outside a checkout")
    args = parser.parse_args(argv or [])

    try:
        pulls = open_pull_requests(args.repo)
    except Exception as exc:  # noqa: BLE001 - not knowing is a failure, not a pass
        print(f"could not list pull requests: {type(exc).__name__}: {exc}")
        print("Cannot tell whether anything is waiting. Treating as FAILED.")
        return 1

    print(f"{len(pulls)} open pull request(s); ready and untouched over {args.minutes}m is stale")
    print("=" * 72)

    stale: list[str] = []
    unread: list[str] = []
    for pull in pulls:
        number, branch = pull["number"], pull["headRefName"]
        state = pull.get("mergeStateStatus") or "UNKNOWN"
        waited = idle_minutes(pull["updatedAt"])

        if pull.get("isDraft"):
            print(f"  #{number:<5} {describe(waited):>8}  draft        {branch}")
            continue

        # The step before ready (#178): has anyone read THIS head? Timed from
        # the last change, because a push restarts the wait for a reader.
        reading = read_state(pull)
        if reading != "read at head" and waited >= args.minutes:
            unread.append(f"#{number} {branch} — {reading} for {describe(waited)}")
        if state != READY:
            # Not ready is not stale: checks running, review outstanding or a
            # conflict are all someone's turn, and the queue is working.
            print(f"  #{number:<5} {describe(waited):>8}  {state:<12} {branch}")
            continue

        pending = pending_checks(number, args.repo)
        if pending is None:
            print(f"  #{number:<5} {describe(waited):>8}  no checks    {branch}")
        elif pending:
            print(f"  #{number:<5} {describe(waited):>8}  {pending} pending    {branch}")
            continue
        elif waited < args.minutes:
            print(f"  #{number:<5} {describe(waited):>8}  ready        {branch}")
            continue

        author = (pull.get("author") or {}).get("login", "?")
        stale.append(
            f"#{number} {branch} — ready and untouched for {describe(waited)} (author {author})"
        )
        print(f"  #{number:<5} {describe(waited):>8}  STALE        {branch}")

    print("=" * 72)
    if stale:
        print(f"  {len(stale)} ready and nobody has acted:\n")
        for line in stale:
            print(f"    {line}")
        print(
            "\n  Merging an existing pull request is the release manager's for any\n"
            "  branch. Whose branch it is is not whose turn it is."
        )
    else:
        # Said out loud on a pass too: a check that only speaks when it fails
        # cannot be told apart from one that did not run.
        print(f"  Nothing ready has been waiting over {args.minutes}m.")

    if unread:
        print(f"\n  {len(unread)} waiting on a reader at head for over {args.minutes}m:\n")
        for line in unread:
            print(f"    {line}")
        print("\n  'Unread' means no Reviewed-SHA line; nothing records who was ASKED.")
    else:
        print(
            f"  Every open pull request has a verdict at head, or changed within {args.minutes}m."
        )

    # Informational only: parking a pushed branch with no PR is legitimate.
    try:
        parked = branches_without_pull_request(args.repo)
    except Exception as exc:  # noqa: BLE001 - said, not hidden; it gates nothing
        print(f"\n  could not list branches ({type(exc).__name__}); pushed-with-no-PR not checked")
    else:
        if parked:
            print(f"\n  {len(parked)} pushed branch(es) with no pull request of any state")
            print("  (reported, not failed -- parking is allowed; this is so it is seen):\n")
            for name in parked:
                print(f"    {name}")
        else:
            print("  No pushed branch is without a pull request.")

    return 1 if stale or unread else 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))
