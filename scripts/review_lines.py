#!/usr/bin/env python3
"""Read the `Reviewed-SHA:` verdict lines on a pull request, and say what they
are claims ABOUT.

WHY THIS EXISTS. Every session here authenticates as the same GitHub account,
so `gh pr review --approve` is refused as self-approval and `reviewDecision`
never reaches `APPROVED`. The team's review record is therefore a convention:
a comment whose **last non-empty line** reads

    Reviewed-SHA: <40-hex> verdict=approved|changes-requested|blocked reviewer=<session>

A convention has no validator, so every failure it has had has been silent.
This reports; it does not decide.

**IT DOES NOT COMPUTE CONSENT.** Counting verdicts into a merge decision
would turn a written convention into an authorisation mechanism, and no such
mechanism exists here — branch protection does not distinguish these sessions
from the user. A reader reports; a person decides. If you find yourself adding
`--is-approved`, that is the line.

THE SIX LOCATION STATES. **`MALFORMED` is not among them** -- it is a
property of the line's SHAPE, asked on its own axis, and listing it here
was how the first version of this docstring came to say FIVE while
`Location.label` returned six. Found by policyforge-ba, and it is the same
partition-that-does-not-add-up as #229.

The SHA resolves:

    AT HEAD      the PR's current head. The only state that counts.
    STALE        a real commit, an ancestor of head, but not head.
    ELSEWHERE    a real commit NOT an ancestor of this head -- reviewed
                 against a pre-rebase history. Neither valid nor stale,
                 and the state no reader here had before #204.

The SHA resolves to nothing, and then what matters is whether the REVIEW
survives:

    RECONSTRUCTED  some prefix names a commit ON THIS BRANCH. The prefix is
                   evidence the reviewer read this PR: a correct review
                   with a broken anchor. Recoverable, and possibly also
                   stale -- a second axis, reported alongside.
    MISANCHORED    some prefix names a commit NOT on this branch. What was
                   reviewed is unknown. Not recoverable.
    FABRICATED     no prefix resolves. Nobody read anything identifiable.

**SHAPE AND LOCATION ARE INDEPENDENT QUESTIONS AND ARE ASKED INDEPENDENTLY.**
policyforge-9b's version chained them as `if`/`elif`, so a line that failed
the shape test never had its ancestry asked -- and the tool reported *"a real
review a strict reader would lose"* about a commit the PR had never carried.
**It credited a review that was not there**, which is the understating
direction: nobody catches that by reading output they expected to be right. A
line can carry both faults and the report has to be able to say so.

A STALE APPROVAL AND A STALE BLOCK ARE OPPOSITE FACTS. An expiring approval
is the safe direction -- the work changed, read it again. An expiring
`changes-requested` is the unsafe one: the author pushes something unrelated
and an unanswered objection silently becomes `blocking verdicts at head: 0`.
That exact line told policyforge-1d nothing was sitting with them on #221
while 9b's block stood untouched.

ONLY THE OBJECTOR RETIRES AN OBJECTION, AND ORDER DECIDES (#237). Each
reviewer's lines are walked in posting order. A block is retired only by a
LATER approval from the SAME reviewer, at any SHA, so an approval from
anyone else never retires it and silence stays silence. That gives three
states, reported apart:

    OPEN                      nothing retired it -- shown whatever its SHA
    RETIRED, approval stale   the objector answered it, then the head moved:
                              re-read, which is the safe direction
    RETIRED at head           silent; a warning that fires on resolved
                              objections trains the reader to ignore it

This used to be decided by position alone: a block was suppressed when its
reviewer had any approval at head. So "answered, and the head moved on"
printed the same STALE BLOCK as "never answered", and a block posted AFTER
its reviewer's own approval was suppressed -- the unsafe direction.

No field in the line names which objection an approval answers, and none is
needed: only the objector can retire one, and an objector who approves while
another concern stands can post `changes-requested` last.

RETIREMENT MATCHES `reviewer=` AS A STRING, so it only works across a
session rename if both lines carry the same stable handle. A line signed
with anything else -- a per-run session name -- is flagged by name rather
than silently treated as a new reviewer.

THE POPULATION IS CHECKED AGAINST A SECOND DERIVATION IN THE SAME UNIT.
A reader that fetches 3 of 8 comments and reports those 3 cleanly would put
this project's dominant failure of the week inside the instrument that
adjudicates every other instrument. So:

    gh api repos/<o>/<r>/issues/<n> --jq .comments   a count GitHub maintains
    gh pr view <n> --json comments | length          the list this process got

Independent in *dimension* -- server-side metadata against a paginated client
fetch -- which is the property a cruder same-shape census would have lacked
(#228). Measured on live PRs: #229 3 vs 3, #231 2 vs 2. A short fetch refuses
rather than reports.

**The standing warning for this file specifically**, policyforge-b5's
formulation: *the shrink is invisible precisely because the check was made
more specific.* Every narrowing of the line pattern below improves what it
asserts and silently reduces what it covers. A parser for a line format gets
narrowed repeatedly, so before tightening `_VERDICT`, check that the number of
lines found did not drop.

Usage:

    python scripts/review_lines.py 229
    python scripts/review_lines.py 229 --repo owner/name
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone

#: The canonical owner since the transfer (#244). The old path still works
#: through GitHub's redirect, which is why nothing failed while it read
#: `rdazzlebot` -- and why it would keep "working" if anything were ever
#: created at the old name. Overridable with `--repo`.
REPO = "rdazzleman/policyforge"

#: The convention's line. Anchored to the END of the comment because a quoted
#: line is otherwise indistinguishable from a given one -- **discussing a
#: review would create one**, including retracting it.
#:
#: It is anchored at LINE START as well. Measured across the corpus, six
#: occurrences of the key are prose -- people discussing the convention --
#: and a reader matching mid-line credits all six as verdicts.
#:
#: **MATCH LOOSELY, REPORT STRICTLY.** The fields are captured as
#: non-whitespace runs and validated afterwards, rather than being required
#: to be clean in order to match at all. A pattern that demands well-formed
#: fields cannot report a malformed one -- it drops the line, and a dropped
#: line is indistinguishable from no review.
#:
#: This is not hypothetical. Measured by policyforge-9b across all 60 PRs,
#: 81 occurrences, and the first version of THIS file silently dropped two
#: of the four real shapes:
#:
#:     0374a18…                  a terminal's truncation marker, pasted
#:     reviewer=policyforge-80** markdown bold bleeding into the value
#:
#: Both are real verdicts by real reviewers. Demanding `[0-9a-f]{4,40}\s`
#: made the first vanish because the next character was `…` rather than a
#: space, which is the understating direction in the tool whose entire job
#: is to say what was reviewed.
_VERDICT = re.compile(
    r"^\s*Reviewed-SHA:\s+(?P<sha>\S+)\s+"
    r"verdict=(?P<verdict>\S+)\s+"
    r"reviewer=(?P<reviewer>\S+)\s*$"
)

#: Trailing characters that are formatting rather than value. Stripped
#: before comparing, and **reported** rather than silently removed.
_TRAILING_NOISE = "*_`.,;:)]}…"

VERDICTS = ("approved", "changes-requested", "blocked")
OBJECTIONS = ("changes-requested", "blocked")

#: The team's stable reviewer handles (convention of 2026-09-23): the name
#: each session had before its first rename. Session names change every run,
#: so a verdict signed with one cannot be matched to the same reader's other
#: verdicts. A handle added to the team is added here.
STABLE_HANDLES = frozenset(
    f"policyforge-{handle}" for handle in ("80", "1d", "9b", "ba", "b5", "5b")
)


def _gh(*args: str) -> str:
    exe = shutil.which("gh") or r"C:\Program Files\GitHub CLI\gh.exe"
    result = subprocess.run(
        [exe, *args], capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    if result.returncode != 0:
        raise RuntimeError(f"gh {' '.join(args)} failed:\n{result.stderr.strip()}")
    return result.stdout


def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], capture_output=True, text=True, encoding="utf-8", errors="replace"
    )


def clean(value: str) -> tuple[str, str]:
    """Split a captured field into its value and the noise around it.

    Returns `(value, noise)` so the caller can report the noise instead of
    pretending it was not there. `0374a18…` -> `("0374a18", "…")`.
    """
    stripped = value.rstrip(_TRAILING_NOISE)
    return stripped, value[len(stripped) :]


@dataclass(frozen=True)
class Shape:
    """What the line looks like. Asked without reference to the repository."""

    well_formed: bool  # exactly 40 hex, after cleaning
    verdict_known: bool
    sha_noise: str = ""
    reviewer_noise: str = ""

    @property
    def label(self) -> str:
        return "well-formed" if self.well_formed else "MALFORMED"

    @property
    def faults(self) -> list[str]:
        """Every fault, not the first one. A line can carry several."""
        found = []
        if not self.well_formed:
            found.append("MALFORMED")
        if not self.verdict_known:
            found.append("UNKNOWN VERDICT")
        if self.sha_noise:
            found.append(f"SHA has trailing {self.sha_noise!r}")
        if self.reviewer_noise:
            found.append(f"reviewer has trailing {self.reviewer_noise!r}")
        return found


def longest_resolving_prefix(sha: str) -> tuple[int, str]:
    """Walk back until a prefix of `sha` names a real commit.

    Returns `(length, full_sha)`, or `(0, "")` if none does.

    **This is the property, and it deliberately has no length in it.**
    The first version of this requirement keyed on *exactly eight common
    characters*, because the instance that prompted it had eight. Measured:
    `git log --oneline` in this repository abbreviates to **seven**, so the
    eighth character matched at one chance in sixteen. A detector keyed on
    8 would have classified that instance correctly by coincidence and
    misclassified the next seven-character case fifteen times out of
    sixteen. policyforge-80 caught its own spec doing it.

    Walking down from 39 terminates: every prefix of a real SHA resolves,
    and a prefix shorter than 4 is refused by git anyway.
    """
    for length in range(min(len(sha), 39), 3, -1):
        resolved = _git("rev-parse", "--verify", f"{sha[:length]}^{{commit}}")
        if resolved.returncode == 0:
            return length, resolved.stdout.strip()
    return 0, ""


@dataclass(frozen=True)
class Location:
    """Where the SHA sits. Asked without reference to the line's shape.

    **Separate from `Shape` because they are separate questions**, and the
    defect this file exists partly to avoid was asking the second only when
    the first passed.
    """

    resolves: bool
    at_head: bool
    ancestor_of_head: bool
    #: When the SHA itself resolves to nothing: how much of it does, and to
    #: what. Zero and "" when no prefix resolves either.
    prefix_length: int = 0
    prefix_target: str = ""
    #: Is the commit the prefix names ON THIS PR'S BRANCH -- not merely
    #: equal to its current head. **The state is a property of the line
    #: PLUS what you compare it against**, and comparing to the head makes
    #: it drift: a line classified RECONSTRUCTED silently becomes the
    #: serious state the moment its author pushes again, with no event,
    #: no diff, and nothing about the line having changed.
    #:
    #: Measured on a real line on #230: prefix `504994f4` names
    #: 504994f480d9, which WAS the head when the line was written and is
    #: now an ancestor of 5938199. Head-equality called it MISANCHORED.
    #: policyforge-80 found it by RUNNING its classifier rather than by
    #: reviewing the spec -- the third correction to this spec, and the
    #: only one that needed the thing to exist first.
    prefix_on_branch: bool = False
    prefix_is_head: bool = False

    @property
    def label(self) -> str:
        if self.resolves:
            if self.at_head:
                return "AT HEAD"
            return "STALE" if self.ancestor_of_head else "ELSEWHERE"
        # A well-formed SHA naming no object splits three ways, and the
        # three differ in whether the REVIEW survives.
        if not self.prefix_target:
            return "FABRICATED"
        if self.prefix_on_branch:
            # The prefix names a real commit OF THIS PR: evidence the
            # reviewer read this branch. A correct review with a broken
            # anchor. Recoverable -- and possibly ALSO stale, which is a
            # second independent axis, not a replacement for this one.
            return "RECONSTRUCTED"
        # The prefix names something else, so what was read is unknown.
        # Not recoverable, and the worse of the two.
        return "MISANCHORED"

    @property
    def diagnosis(self) -> str:
        """Why the SHA names nothing, in terms that point at the tooling.

        *"names no commit; `504994f4` is the head of this PR, so this was
        probably extended from an abbreviated display"* is a diagnosis. **An
        accusation would be "fabricated".** Three sessions produced one of
        these in a day; the remedy is in the display, not in the discipline,
        because the old rule -- never lengthen an abbreviated SHA -- asks a
        person to resist something the tooling hands them.
        """
        if self.resolves or not self.prefix_target:
            return ""
        if self.prefix_is_head:
            what = "the head of this PR"
        elif self.prefix_on_branch:
            what = "an earlier commit of this PR, so the review is also STALE"
        else:
            what = "a commit NOT on this branch"
        return (
            f"names no commit, but its first {self.prefix_length} characters do: "
            f"{self.prefix_target[:12]} ({what}). Probably extended from an "
            f"abbreviated display."
        )


@dataclass(frozen=True)
class Line:
    sha: str
    verdict: str
    reviewer: str
    shape: Shape
    location: Location

    @property
    def counts(self) -> bool:
        """Only a well-formed line at head is a verdict on this code."""
        return self.shape.well_formed and self.location.at_head


def shape_of(sha: str, verdict: str, reviewer: str = "") -> Shape:
    hexed, sha_noise = clean(sha)
    verdict_value, _ = clean(verdict)
    _, reviewer_noise = clean(reviewer)
    return Shape(
        well_formed=len(hexed) == 40 and all(c in "0123456789abcdef" for c in hexed.lower()),
        verdict_known=verdict_value in VERDICTS,
        sha_noise=sha_noise,
        reviewer_noise=reviewer_noise,
    )


def location_of(sha: str, head: str) -> Location:
    """Resolve `sha` in this clone and place it relative to `head`.

    Asked for **every** line, whatever its shape. A short SHA that resolves
    is still somewhere, and where it is may be the finding.
    """
    sha, _ = clean(sha)
    resolved = _git("rev-parse", "--verify", f"{sha}^{{commit}}")
    if resolved.returncode != 0:
        length, target = longest_resolving_prefix(sha)
        return Location(
            resolves=False,
            at_head=False,
            ancestor_of_head=False,
            prefix_length=length,
            prefix_target=target,
            prefix_on_branch=bool(target)
            and _git("merge-base", "--is-ancestor", target, head).returncode == 0,
            prefix_is_head=bool(target) and target == head,
        )
    full = resolved.stdout.strip()
    return Location(
        resolves=True,
        at_head=full == head,
        ancestor_of_head=_git("merge-base", "--is-ancestor", full, head).returncode == 0,
    )


def verdict_lines(comments: list[dict]) -> list[Line]:
    """Every comment whose LAST NON-EMPTY line is a verdict."""
    found = []
    for comment in comments:
        lines = [ln for ln in (comment.get("body") or "").splitlines() if ln.strip()]
        if not lines:
            continue
        match = _VERDICT.search(lines[-1].strip())
        if match:
            found.append(match.groupdict())
    return found


#: Where an approval must point to retire an objection: a commit of THIS PR.
#: AT HEAD and STALE resolve on the branch; RECONSTRUCTED names no object but
#: its prefix is a commit of this PR, so the reviewer read this branch.
#: ELSEWHERE, MISANCHORED and FABRICATED point off the branch or at nothing,
#: so what was approved is not this code -- they leave the objection OPEN.
#: Found by policyforge-9b on #284: well-formed alone let all three retire.
RETIRING_LOCATIONS = frozenset({"AT HEAD", "STALE", "RECONSTRUCTED"})


def objection_states(lines: list[Line]) -> list[tuple[Line, str, Line | None]]:
    """Every objection, in posting order, with its state and what retired it.

    `lines` must be in posting order. The state is `OPEN`, `RETIRED STALE`
    or `RETIRED AT HEAD`. Only a well-formed approval retires: a malformed
    one might be crediting a review that was not there, so it leaves the
    objection OPEN, which is the safe direction.

    Every later approval from the objector is considered, not the first
    one. On #273 the objector approved at a stale head, objected again, then
    approved at head: the first approval alone called the first objection
    "retired, approval stale" -- a re-read notice about a question its own
    reviewer had since settled at head.
    """
    states = []
    for index, line in enumerate(lines):
        if line.verdict not in OBJECTIONS:
            continue
        retiring = [
            later
            for later in lines[index + 1 :]
            if later.reviewer == line.reviewer
            and later.verdict == "approved"
            and later.shape.well_formed
            and later.location.label in RETIRING_LOCATIONS
        ]
        at_head = [later for later in retiring if later.counts]
        if at_head:
            states.append((line, "RETIRED AT HEAD", at_head[-1]))
        elif retiring:
            states.append((line, "RETIRED STALE", retiring[-1]))
        else:
            states.append((line, "OPEN", None))
    return states


def fetch(number: int, repo: str) -> tuple[str, list[dict], int]:
    """Return (head, comments, the count GitHub reports).

    The third value is the second derivation. It is fetched from a different
    endpoint than the list, which is what makes it able to disagree.
    """
    data = json.loads(
        _gh("pr", "view", str(number), "--repo", repo, "--json", "headRefOid,comments")
    )
    reported = int(_gh("api", f"repos/{repo}/issues/{number}", "--jq", ".comments").strip())
    return data["headRefOid"], data.get("comments") or [], reported


def report(number: int, repo: str) -> int:
    head, comments, reported = fetch(number, repo)

    # THE FIRST THREE LINES, deliberately. A report that was true when taken
    # and false when read cost a real misroute today -- #229 was described as
    # having zero verdicts by someone who measured before the verdict was
    # posted. The reader of this output has to see the staleness and the
    # population BEFORE the verdicts, not in a footer.
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")
    print(f"#{number} on {repo} -- read at {now}")
    print(f"head {head}")
    print(f"{len(comments)} comment(s) fetched; GitHub reports {reported}")

    if len(comments) != reported:
        print(
            f"\nPOPULATION SHORT: GitHub reports {reported} comment(s) on "
            f"#{number}; this fetch returned {len(comments)}.\n"
            f"  Every verdict below would be a claim about a truncated list.",
            file=sys.stderr,
        )
        return 2

    raw = verdict_lines(comments)
    lines = [
        Line(
            sha=r["sha"],
            verdict=r["verdict"],
            reviewer=r["reviewer"],
            shape=shape_of(r["sha"], r["verdict"], r["reviewer"]),
            location=location_of(r["sha"], head),
        )
        for r in raw
    ]

    print(f"{len(lines)} verdict line(s)\n")
    if not lines:
        print("  No verdict lines. That is 'nobody has posted one', NOT 'no")
        print("  objection stands' -- a reader cannot tell those apart and")
        print("  neither can this tool.")
        return 0

    for line in lines:
        # Both facts, always. A line can be MALFORMED *and* ELSEWHERE, and
        # the version that chained these credited a review that was not there.
        marks = [line.location.label, *line.shape.faults]
        print(f"  {line.sha[:12]:14} {line.verdict:18} {line.reviewer:16} {' + '.join(marks)}")

    # Objections by state (#237). Only the objector's own later approval
    # retires one; nothing about the SHA does.
    states = objection_states(lines)
    still_open = [line for line, state, _ in states if state == "OPEN"]
    answered_then_moved = [(line, by) for line, state, by in states if state == "RETIRED STALE"]
    if still_open:
        print(
            f"\n!! {len(still_open)} OPEN OBJECTION(S) — no later approval from the objector.\n"
            f"   Expiry is not resolution, and another reviewer's approval does not answer it."
        )
        for line in still_open:
            print(f"     {line.reviewer} at {line.sha[:12]} ({line.location.label})")
    if answered_then_moved:
        print(
            f"\n   {len(answered_then_moved)} objection(s) retired by their own reviewer at a "
            f"commit that is no longer head.\n"
            f"   Answered, then the code moved: read the delta again."
        )
        for line, by in answered_then_moved:
            print(
                f"     {line.reviewer} objected at {line.sha[:12]}, approved at {by.sha[:12]} "
                f"({by.location.label})"
            )

    # Retirement matches `reviewer=` as a string, so a perishable name makes
    # the matching partial. Said, so it is not read as whole.
    unknown = sorted({line.reviewer for line in lines if line.reviewer not in STABLE_HANDLES})
    if unknown:
        print(
            f"\n?? {len(unknown)} reviewer name(s) that are not a stable handle: "
            f"{', '.join(unknown)}\n"
            f"   A line signed this way can neither retire nor be retired by a "
            f"handle-signed line."
        )

    print("\n  This is a report. It does not compute consent, and no count")
    print("  below is an authorisation -- a person decides.")
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Read a PR's Reviewed-SHA verdict lines.")
    parser.add_argument("number", type=int)
    parser.add_argument("--repo", default=REPO)
    args = parser.parse_args(argv)
    return report(args.number, args.repo)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
