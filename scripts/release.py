#!/usr/bin/env python3
"""Cut a release as an ordered list of gated steps, not a remembered procedure.

WHY THIS EXISTS (#255, split from #198). The cut used to be prose in
CONTRIBUTING.md: assemble the changelog, bump the version, merge to main,
tag, update the formula, install it, push it, check it. #198's evidence was
a step skipped because nothing made it come first -- the container install
at 1.6.0 ran only because the user asked. `release_check.py` (#200) made the
skip VISIBLE after the fact; this makes it impossible, because each step
checks the one before it actually happened.

THE CONTRACT, stated once and held by every step:

- **Each step has a GATE that must hold before it acts, and a POSTCONDITION
  checked after.** Both compare values and print them. None reads an exit
  status and calls it a result -- the `cmd; echo; tail` shape
  `release_check.py`'s header records.
- **A step whose postcondition already holds is reported done and skipped**,
  so re-running after an interruption, or after the user's merge to main,
  resumes where the release actually is.
- **`--dry-run` is the default.** It evaluates gates until the first step
  that would ACT, then lists the rest as not reached, "reached k of N". A
  later gate evaluated against a state an earlier step has not produced
  would be a measurement of nothing.
- **An OUTWARD step -- one that changes something outside this clone (push,
  tag, GitHub Release, the tap) -- needs `--execute` AND its key typed.** A
  stray invocation cannot cut a release. **`release-pr`'s key is asked
  BEFORE the changelog step writes anything** (policyforge-ba on #348):
  declining it after the cut was written left a dirty tree that stopped
  every re-run at clean-tree. A cut interrupted any other way (a failed
  postcondition, Ctrl-C) still stops there, and clean-tree prints the
  `git restore` that puts it back rather than running it.
- **The train is read from the server** (`git ls-remote`), never from this
  clone's `origin/*` refs, which answer about the last fetch.
- **The script never merges to main.** Final approval to main is the user's,
  in GitHub, and the ruleset makes it impossible anyway. That step is a WAIT:
  it reports what it is waiting for and exits 5, and a re-run after the
  user's merge continues.

TWO INSTALL TESTS (the user's ruling on #255, relayed by 80), the first of
them BEFORE the user's approval ("Install first", the user to 1d directly,
2026-09-25, #381): the release PR HEAD's archive is installed in a clean
container and the result posted on the tracking issue as a
`Release-install:` record, so the user approves main with it in hand. The
wait refuses a head that moved after the install (the installed SHA is read
from the record, never fetched at the moment of checking), and main's step
then proves its merge tree is that head's, so the install carries across the
merge. Then the CANDIDATE formula (the tag's archive) is installed before it
is published to the tap, and `release_check.py` checks the PUBLISHED formula
last.

EXIT CODES: 0 done; 5 waiting on the user; 6 an outward step not confirmed;
10+i a failed gate at step i; 40+i a failed postcondition at step i; 2 a
version that is not X.Y.Z. A wrong tree is not a refusal before the steps:
it fails at step 2 (clean-tree), and there is no platform check -- a
Windows host with Docker is what the container steps need.

Usage:

    python scripts/release.py 1.6.1              # dry-run: what would happen
    python scripts/release.py 1.6.1 --execute    # act, step by step
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import changelog_fragments  # noqa: E402
import release_check  # noqa: E402

TRAIN_PREFIX = "release/"
TAP_REPOSITORY = f"{release_check.OWNER}/homebrew-tap"
TAP_FORMULA_PATH = "Formula/policyforge.rb"
CONTAINER_IMAGE = release_check.CONTAINER_IMAGE

CHECK, ACT, WAIT = "check", "act", "wait"


@dataclass
class Check:
    """A gate or postcondition's answer, with the values it compared."""

    ok: bool
    measured: list[str] = field(default_factory=list)


@dataclass
class Step:
    key: str
    title: str
    kind: str  # CHECK: gate only; ACT: gate, act, postcondition; WAIT: the user acts
    gate: Callable[[Context], Check]
    post: Callable[[Context], Check]
    act: Callable[[Context], None] | None = None
    outward: bool = False
    #: One line saying what the step would do, for the dry-run.
    would: str = ""
    #: The key of a LATER outward step this one commits the run to. It is
    #: asked for here, before this step writes anything, and not again when
    #: that step is reached in the same run (policyforge-ba on #348).
    commits_to: str = ""


@dataclass
class Context:
    """Everything a step touches outside Python, injectable for tests."""

    version: str
    root: Path = REPO_ROOT
    #: Runs argv, returns CompletedProcess(returncode, stdout, stderr). Never raises.
    run: Callable[[list[str]], subprocess.CompletedProcess] = None  # type: ignore[assignment]
    #: HTTP status of a URL.
    status_of: Callable[[str], int] = None  # type: ignore[assignment]
    #: sha256 of the bytes a URL serves.
    hash_url: Callable[[str], str] = None  # type: ignore[assignment]
    #: Installs a formula text in a clean container and checks the installed
    #: package's version is this one: (formula, version) -> (ran, ok, lines).
    install: Callable[[str, str], tuple[bool, bool, list[str]]] = None  # type: ignore[assignment]
    #: Reads the typed confirmation for an outward step.
    confirm: Callable[[str], str] = input
    #: The release's tracking issue, where the two artefact gates read their records.
    tracking: int | None = None
    #: The operator's regenerated and reconciled formula (`--formula`), the
    #: base every formula this script writes is edited from (#389). None
    #: means the published formula, which is right only while the lock is
    #: unchanged since the last release.
    formula_path: Path | None = None
    #: Values steps hand to later steps (main's merge SHA, the candidate formula).
    notes: dict[str, str] = field(default_factory=dict)

    @property
    def tag(self) -> str:
        return f"v{self.version}"

    def git(self, *args: str) -> str:
        return (self.run(["git", "-C", str(self.root), *args]).stdout or "").strip()


# --- the engine --------------------------------------------------------------


def run_steps(steps: list[Step], ctx: Context, *, execute: bool, out=print) -> int:
    """Walk the steps in order; the return value is the exit code."""
    confirmed: set[str] = set()
    for index, step in enumerate(steps, 1):
        out(f"\n[{index}/{len(steps)}] {step.key}: {step.title}")
        done = step.post(ctx) if step.kind != CHECK else Check(False)
        if done.ok:
            for line in done.measured:
                out(f"    {line}")
            out("    already done; skipping")
            continue

        gate = step.gate(ctx)
        for line in gate.measured:
            out(f"    gate: {line}")
        if not gate.ok:
            out(f"    GATE FAILED at step {index} ({step.key}); nothing was changed by this step")
            return 10 + index

        if step.kind == CHECK:
            out("    holds")
            continue

        if step.kind == WAIT:
            out(f"    WAITING: {step.would}")
            out("    re-run this command once that has happened; the steps before are done")
            return 5

        if not execute:
            out(f"    would: {step.would}")
            out(
                f"\nDRY RUN: reached {index} of {len(steps)} steps; "
                "the rest depend on this one acting."
            )
            for later in steps[index:]:
                out(f"    not reached: {later.key}: {later.title}")
            return 0

        needs = step.commits_to or (step.key if step.outward else "")
        if needs and needs not in confirmed:
            later = next((s for s in steps if s.key == needs), step)
            prompt = f"    type '{needs}' to {later.would}"
            if needs != step.key:
                prompt += f" (asked now: {step.key} writes the cut, and only {needs} commits it)"
            typed = ctx.confirm(prompt + ": ").strip()
            if typed != needs:
                out(f"    not confirmed (typed {typed!r}); stopping before {step.key}")
                return 6
            confirmed.add(needs)

        assert step.act is not None, f"{step.key} is an ACT step with no action"
        step.act(ctx)
        after = step.post(ctx)
        for line in after.measured:
            out(f"    after: {line}")
        if not after.ok:
            out(f"    POSTCONDITION FAILED at step {index} ({step.key})")
            return 40 + index
    out(f"\nRelease {ctx.tag}: all {len(steps)} steps hold.")
    return 0


# --- the steps ---------------------------------------------------------------


def _versions(ctx: Context) -> tuple[str, str]:
    pyproject = (ctx.root / "pyproject.toml").read_text(encoding="utf-8")
    init = (ctx.root / "src" / "policyforge" / "__init__.py").read_text(encoding="utf-8")
    a = re.search(r'^version = "([^"]+)"', pyproject, re.M)
    b = re.search(r'^__version__ = "([^"]+)"', init, re.M)
    return (a.group(1) if a else "?", b.group(1) if b else "?")


def _milestone_open(ctx: Context) -> Check:
    """Open issues on the version's milestone, by REST, confirmed by search.

    Two instruments because `gh issue list --milestone` returned a false 0 for
    1.6.1 while 19 were open (CLAUDE.md), and zero is the value that lets a
    release out.
    """
    repo = release_check.REPOSITORY
    milestones = ctx.run(["gh", "api", f"repos/{repo}/milestones?state=all&per_page=100"]).stdout
    number = next(
        (m["number"] for m in json.loads(milestones or "[]") if m.get("title") == ctx.version),
        None,
    )
    if number is None:
        return Check(False, [f"no milestone titled {ctx.version!r}"])
    rest = ctx.run(
        [
            "gh",
            "api",
            f"repos/{repo}/issues?milestone={number}&state=open&per_page=100",
            "--jq",
            "[.[]|select(.pull_request|not)]|length",
        ]
    ).stdout.strip()
    search = ctx.run(
        [
            "gh",
            "api",
            "-X",
            "GET",
            "search/issues",
            "-f",
            f'q=repo:{repo} is:issue is:open milestone:"{ctx.version}"',
            "--jq",
            ".total_count",
        ]
    ).stdout.strip()
    ok = rest == "0" and search == "0"
    return Check(
        ok,
        [
            f"open issues on {ctx.version}: REST {rest or '?'}, search {search or '?'} "
            "(both must be 0)"
        ],
    )


def _server_tip(ctx: Context, branch: str) -> str:
    """`branch`'s tip ON THE SERVER, never this clone's `origin/<branch>` ref.

    policyforge-ba on #348, measured with a second clone: nothing here fetched
    the train, so a gate reading `origin/release/X` answered about whenever
    this clone last fetched. After a late merge pushed from elsewhere,
    clean-tree AND notes-measured both passed on the stale tip, the second on
    exactly the stale measurement it exists to refuse. `ls-remote` asks the
    server every time. No answer is "", which fails every gate that reads it.
    """
    return _remote_tip(ctx, "origin", branch)


def _remote_tip(ctx: Context, remote: str, branch: str) -> str:
    """`branch`'s tip as `remote` reports it now; "" when it does not answer."""
    out = ctx.run(["git", "-C", str(ctx.root), "ls-remote", remote, f"refs/heads/{branch}"])
    for line in (out.stdout or "").splitlines():
        sha, _, ref = line.partition("\t")
        if ref.strip() == f"refs/heads/{branch}" and re.fullmatch(r"[0-9a-f]{40}", sha):
            return sha
    return ""


#: What steps 5 and 6 write. A dirty tree made only of these is an
#: interrupted cut, and clean-tree says how to put it back.
CUT_PATHS = ("CHANGELOG.md", "changelog.d/", "pyproject.toml", "src/policyforge/__init__.py")


def _dirty_paths(ctx: Context) -> list[str]:
    """Paths `git status --porcelain` names, read unstripped: its first column
    is significant, and `ctx.git` strips the output."""
    out = ctx.run(["git", "-C", str(ctx.root), "status", "--porcelain"]).stdout or ""
    return [line[3:] for line in out.splitlines() if line.strip()]


def _train_tree(ctx: Context) -> Check:
    # THIS version's train, not any train (policyforge-b5 on #348): with a
    # prefix test, `release.py 1.7.0` on a release/1.6.1 checkout passed
    # here and cut 1.7.0 from 1.6.1's code, and notes-measured, reading
    # release/1.7.0's tip, could not see it.
    train = f"{TRAIN_PREFIX}{ctx.version}"
    branch = ctx.git("rev-parse", "--abbrev-ref", "HEAD")
    head = ctx.git("rev-parse", "HEAD")
    remote = _server_tip(ctx, branch) if branch == train else ""
    cut = _release_pr(ctx).get("headRefOid", "")
    dirty = _dirty_paths(ctx)
    ok = branch == train and head in {remote, cut} - {""} and not dirty
    measured = [
        f"branch {branch!r} (must be {train!r})",
        f"HEAD {head[:12]}: origin/{branch} ON THE SERVER {remote[:12] or '-'}, "
        f"release PR head {cut[:12] or '-'} (must be one)",
        f"uncommitted changes: {len(dirty)} (must be 0)",
    ]
    if dirty and all(path.startswith(CUT_PATHS) for path in dirty):
        # Steps 5 and 6 wrote these and the run stopped before release-pr
        # committed them (a failed postcondition, a failed commit, Ctrl-C).
        # Said, not done: discarding a working tree is the operator's call.
        measured.append(
            "these are only the cut's own files, from an interrupted run; to start "
            "the cut again: git restore --source=HEAD --staged --worktree -- " + " ".join(CUT_PATHS)
        )
    return Check(ok, measured)


def _fragments_ready(ctx: Context) -> Check:
    found = changelog_fragments.fragments(ctx.root / "changelog.d")
    problems = changelog_fragments.check(ctx.root / "changelog.d")
    return Check(
        bool(found) and not problems,
        [
            f"fragments: {len(found)} (must be > 0)",
            f"fragment problems: {len(problems)} (must be 0)",
        ],
    )


def _changelog_cut(ctx: Context) -> Check:
    left = changelog_fragments.fragments(ctx.root / "changelog.d")
    text = (ctx.root / "CHANGELOG.md").read_text(encoding="utf-8")
    has = f"\n## {ctx.version}\n" in "\n" + text
    return Check(
        has and not left,
        [f"`## {ctx.version}` in CHANGELOG.md: {has}", f"fragments left: {len(left)}"],
    )


def _assemble(ctx: Context) -> None:
    changelog_fragments.main(["--version", ctx.version])


def _bump_ready(ctx: Context) -> Check:
    a, b = _versions(ctx)
    return Check(a == b, [f"pyproject {a} / __version__ {b} (must agree before bumping)"])


def _bumped(ctx: Context) -> Check:
    a, b = _versions(ctx)
    return Check(
        a == b == ctx.version, [f"pyproject {a} / __version__ {b} (must both be {ctx.version})"]
    )


def _bump(ctx: Context) -> None:
    for path, pattern in (
        (ctx.root / "pyproject.toml", r'^(version = ")[^"]+(")'),
        (ctx.root / "src" / "policyforge" / "__init__.py", r'^(__version__ = ")[^"]+(")'),
    ):
        text = path.read_text(encoding="utf-8")
        path.write_text(
            re.sub(pattern, rf"\g<1>{ctx.version}\g<2>", text, count=1, flags=re.M),
            encoding="utf-8",
            newline="\n",
        )


# --- the install pins (#413) --------------------------------------------------
#
# README tells a user without Homebrew to run
# `pipx install git+https://github.com/<owner>/policyforge@vX.Y.Z`. The 1.6.1
# cut moved nothing there, so the released README installed 1.6.0 (5b; 80's
# ruling on #413: the pins stay, and the cut moves them). The population is
# DERIVED, every pin in every tracked text file, and CLASSIFIED rather than
# filtered, so a pin in a new file is rewritten or refused, never skipped:
#
#     instruction   anywhere else     rewritten to this release
#     history       CHANGELOG.md      what a past release said; never touched
#     test          under tests/      fixtures; never touched

#: A pin of `<owner>/policyforge` at a release, as an install command writes
#: it. The owner is captured so a pin naming the redirect's old owner is
#: refused rather than moved (CLAUDE.md: a redirect is not a reference).
#:
#: **Case-insensitive** (policyforge-ba on #430): GitHub resolves
#: `rdazzleman/PolicyForge` as this repository, so a case-sensitive match
#: skipped a pin that installs. The `v` is captured apart, because a tag
#: IS case-sensitive: `@V1.6.0` names no tag, and is refused, not moved.
_PIN_RE = re.compile(r"([A-Za-z0-9_.-]+)/policyforge(?:\.git)?@(v)(\d+\.\d+\.\d+)\b", re.IGNORECASE)
#: The same shape for `git grep -E`, which finds the lines `_PIN_RE` reads.
_PIN_ERE = r"[A-Za-z0-9_.-]+/policyforge(\.git)?@v[0-9]+\.[0-9]+\.[0-9]+"


@dataclass(frozen=True)
class Pin:
    path: str
    line: int
    owner: str
    version: str
    #: The tag's `v` as written; `V` names no tag (git tags are case-sensitive).
    marker: str = "v"

    @property
    def kind(self) -> str:
        if self.path == "CHANGELOG.md":
            return "history"
        if self.path.startswith("tests/"):
            return "test"
        return "instruction"

    @property
    def canonical(self) -> bool:
        return f"{self.owner}/policyforge".lower() == release_check.REPOSITORY.lower()

    def __str__(self) -> str:
        return f"{self.path}:{self.line} {self.owner}/policyforge@v{self.version}"


def _pins(ctx: Context, at: str = "") -> list[Pin] | None:
    """Every pin in every tracked text file, in the working tree or at `at`
    (a commit). None when `git grep` fails: no answer is not zero pins."""
    argv = ["git", "-C", str(ctx.root), "grep", "-n", "-I", "-i", "-E", _PIN_ERE]
    if at:
        argv.append(at)
    out = ctx.run(argv)
    if out.returncode not in (0, 1):  # 1 is "no match"; anything else, no answer
        return None
    found = []
    for row in (out.stdout or "").splitlines():
        if at:
            row = row[len(at) + 1 :]  # `HEAD:path:line:text`
        path, number, text = row.split(":", 2)
        for match in _PIN_RE.finditer(text):
            found.append(Pin(path, int(number), match.group(1), match.group(3), match.group(2)))
    return found


def _pin_lines(pins: list[Pin]) -> list[str]:
    by_kind = {
        kind: [p for p in pins if p.kind == kind] for kind in ("instruction", "history", "test")
    }
    return [f"install pins: {', '.join(f'{k} {len(v)}' for k, v in by_kind.items())}"]


def _pins_ready(ctx: Context) -> Check:
    pins = _pins(ctx)
    if pins is None:
        return Check(False, ["git grep failed, so the pins are unknown (not zero)"])
    instructions = [p for p in pins if p.kind == "instruction"]
    foreign = [p for p in instructions if not p.canonical]
    untagged = [p for p in instructions if p.marker != "v"]
    ctx.notes["pins"] = str(len(instructions))
    return Check(
        not foreign and not untagged,
        [
            *_pin_lines(pins),
            *(f"names another owner, rewrite it by hand first: {p}" for p in foreign),
            *(
                f"`@V` names no tag (tags are case-sensitive), fix it by hand: {p}"
                for p in untagged
            ),
        ],
    )


def _pins_current(ctx: Context) -> Check:
    pins = _pins(ctx)
    if pins is None:
        return Check(False, ["git grep failed, so the pins are unknown (not current)"])
    instructions = [p for p in pins if p.kind == "instruction"]
    stale = [p for p in instructions if p.version != ctx.version or not p.canonical]
    # Conservation: the step moves pins, it never loses one. Known only after
    # the gate has counted them in this run.
    before = ctx.notes.get("pins")
    kept = before is None or int(before) == len(instructions)
    return Check(
        not stale and kept,
        [
            *_pin_lines(pins),
            *(f"not at v{ctx.version}: {p}" for p in stale),
            *([] if kept else [f"instruction pins {before} before, {len(instructions)} after"]),
        ],
    )


def _repin(ctx: Context) -> None:
    pins = _pins(ctx) or []
    for path in sorted({p.path for p in pins if p.kind == "instruction" and p.canonical}):
        file = ctx.root / path
        text = file.read_text(encoding="utf-8")
        text = _PIN_RE.sub(
            lambda m: (
                m.group(0)[: m.start(3) - m.start(0)]
                + ctx.version
                + m.group(0)[m.end(3) - m.start(0) :]
                if f"{m.group(1)}/policyforge".lower() == release_check.REPOSITORY.lower()
                and m.group(2) == "v"
                else m.group(0)
            ),
            text,
        )
        file.write_text(text, encoding="utf-8", newline="\n")


def _release_pr(ctx: Context) -> dict:
    out = ctx.run(
        [
            "gh",
            "pr",
            "list",
            "--repo",
            release_check.REPOSITORY,
            "--base",
            "main",
            "--state",
            "all",
            # By the branch `_open_pr` pushes, not `--search`: search is an
            # index, and it missed a PR created a moment earlier, at the 1.6.1
            # cut (policyforge-9b on #380). `--head` filters the list itself.
            "--head",
            f"9b/release-{ctx.version}",
            "--json",
            "number,state,headRefOid,mergeCommit,title",
        ]
    ).stdout
    # The exact title `_open_pr` writes: a prefix took "Release 1.6.10" for
    # 1.6.1. Then MERGED, then OPEN, before a closed first attempt, whatever
    # order `gh` lists them in (policyforge-b5 on #348).
    prs = [p for p in json.loads(out or "[]") if p.get("title", "") == f"Release {ctx.version}"]
    rank = {"MERGED": 0, "OPEN": 1}
    prs.sort(key=lambda p: rank.get(p.get("state", ""), 2))
    return prs[0] if prs else {}


def _pr_ready(ctx: Context) -> Check:
    return Check(True, ["the cut commit will be pushed and a PR opened against main"])


def _cut_at_head(ctx: Context) -> list[tuple[bool, str]]:
    """Whether HEAD's COMMITTED content is the cut: both versions X, `## X` in
    the changelog, no fragments left, and nothing uncommitted.

    policyforge-ba on #348: the postcondition used to ask only whether a PR
    sat at HEAD. With the commit refused (a hook, no identity), the push sent
    the train tip, a PR opened there, and "ok" was printed over a tree whose
    bump was still uncommitted, so 9.9.9 could have been tagged on 9.9.8 code.
    This reads HEAD, not the working tree, because HEAD is what gets pushed.
    """

    def show(path: str) -> str:
        return ctx.run(["git", "-C", str(ctx.root), "show", f"HEAD:{path}"]).stdout or ""

    a = re.search(r'^version = "([^"]+)"', show("pyproject.toml"), re.M)
    b = re.search(r'^__version__ = "([^"]+)"', show("src/policyforge/__init__.py"), re.M)
    a, b = (a.group(1) if a else "?"), (b.group(1) if b else "?")
    section = f"\n## {ctx.version}\n" in "\n" + show("CHANGELOG.md")
    listed = ctx.run(["git", "-C", str(ctx.root), "ls-tree", "--name-only", "HEAD", "changelog.d/"])
    left = [
        name
        for name in (listed.stdout or "").splitlines()
        if name.endswith(".md") and Path(name).name not in changelog_fragments.NOT_A_FRAGMENT
    ]
    dirty = _dirty_paths(ctx)
    pins = _pins(ctx, "HEAD")
    stale = (
        None
        if pins is None
        else [p for p in pins if p.kind == "instruction" and p.version != ctx.version]
    )
    return [
        (
            a == b == ctx.version,
            f"at HEAD: pyproject {a} / __version__ {b} (must both be {ctx.version})",
        ),
        (section, f"at HEAD: `## {ctx.version}` in CHANGELOG.md: {section}"),
        (not left, f"at HEAD: fragments left: {len(left)} (must be 0)"),
        (
            stale == [],
            f"at HEAD: install pins not at v{ctx.version}: "
            + ("unknown, git grep failed" if stale is None else str(len(stale))),
        ),
        (not dirty, f"uncommitted changes: {len(dirty)} (must be 0: the cut is committed)"),
    ]


def _pr_open(ctx: Context) -> Check:
    pr = _release_pr(ctx)
    head = ctx.git("rev-parse", "HEAD")
    at_head = bool(pr) and (pr.get("state") == "MERGED" or pr.get("headRefOid") == head)
    content = _cut_at_head(ctx)
    measured = [
        f"release PR: {'#' + str(pr['number']) + ' ' + pr['state'] if pr else 'none'}, "
        f"at HEAD {head[:12]}: {at_head}",
        *(line for _, line in content),
    ]
    if ctx.notes.get("release-pr"):
        measured.append(ctx.notes["release-pr"])
    return Check(at_head and all(ok for ok, _ in content), measured)


def _open_pr(ctx: Context) -> None:
    """Commit, push, open, and STOP at the first that fails (policyforge-ba
    on #348): a refused commit followed by a push sends the train tip under
    the release's name. What failed is left for the postcondition to print."""
    branch = f"9b/release-{ctx.version}"
    for argv in (
        ["git", "-C", str(ctx.root), "commit", "-am", f"Release {ctx.version}"],
        ["git", "-C", str(ctx.root), "push", "origin", f"HEAD:refs/heads/{branch}"],
        [
            "gh",
            "pr",
            "create",
            "--repo",
            release_check.REPOSITORY,
            "--base",
            "main",
            "--head",
            branch,
            "--title",
            f"Release {ctx.version}",
            "--body",
            f"The {ctx.version} cut, prepared by scripts/release.py. "
            "Merging it is the user's approval.",
        ],
    ):
        proc = ctx.run(argv)
        if proc.returncode != 0:
            said = ((proc.stderr or "") + (proc.stdout or "")).strip().splitlines()
            what = " ".join(argv[3:5] if argv[0] == "git" else argv[:3])
            ctx.notes["release-pr"] = (
                f"`{what}` exited {proc.returncode}, so nothing after it ran"
                + (f": {said[-1]}" if said else "")
            )
            return


def _pr_still_open(ctx: Context) -> Check:
    """The wait's gate: there is a release PR to wait FOR.

    policyforge-ba on #348: if the only release PR was closed unmerged (at
    HEAD, so release-pr counts as done), the wait said "waiting" forever.
    Safe, but silent. Now it stops and says the PR is closed."""
    pr = _release_pr(ctx)
    state = pr.get("state", "") if pr else ""
    return Check(
        state == "OPEN",
        [
            f"release PR: {'#' + str(pr['number']) + ' ' + state if pr else 'none'} "
            "(must be OPEN to wait for; a CLOSED one will never be merged: "
            "reopen it, or close the cut and start again)"
        ],
    )


def _main_merged(ctx: Context) -> Check:
    pr = _release_pr(ctx)
    merge = (pr.get("mergeCommit") or {}).get("oid", "") if pr else ""
    if not merge:
        return Check(False, [f"release PR merged into main: {'no' if pr else 'no PR'}"])
    ctx.run(["git", "-C", str(ctx.root), "fetch", "-q", "origin", "main"])
    on_main = (
        ctx.run(
            ["git", "-C", str(ctx.root), "merge-base", "--is-ancestor", merge, "origin/main"]
        ).returncode
        == 0
    )
    # Against the cut commit THIS script made (local HEAD, which survives
    # the exit-5 re-run), never against the PR's head as fetched now: that
    # value passes by construction if anything was pushed to the release
    # branch after step 5 (policyforge-9b on #348, the --match-head-commit
    # failure the charge names).
    cut = ctx.git("rev-parse", "HEAD")
    head_is_cut = pr.get("headRefOid") == cut
    same_tree = ctx.git("rev-parse", f"{merge}^{{tree}}") == ctx.git("rev-parse", f"{cut}^{{tree}}")
    ok = on_main and head_is_cut and same_tree
    if ok:
        ctx.notes["main_sha"] = merge
    return Check(
        ok,
        [
            f"merge commit {merge[:12]} on origin/main: {on_main}",
            f"the PR's head {str(pr.get('headRefOid'))[:12]} is the cut commit {cut[:12]}: "
            f"{head_is_cut}",
            f"the merge's tree equals the cut commit's: {same_tree}",
        ],
    )


def _no_tag(ctx: Context) -> Check:
    local = ctx.git("tag", "--list", ctx.tag)
    remote = (
        ctx.run(["git", "-C", str(ctx.root), "ls-remote", "--tags", "origin", ctx.tag]).stdout or ""
    ).strip()
    return Check(
        not local and not remote,
        [f"tag {ctx.tag}: local {bool(local)}, remote {bool(remote)} (both must be absent)"],
    )


def _base_formula(ctx: Context) -> str:
    """The formula this cut edits: `--formula` if given, else the published one.

    CONTRIBUTING's release step regenerates the resource stanzas with
    `brew update-python-resources` and reconciles each to the lock. This is
    how that file reaches the script, instead of being published to the
    tap before the release to get read (#389)."""
    if ctx.formula_path is not None:
        return ctx.formula_path.read_text(encoding="utf-8")
    return release_check.fetch_formula()


def _formula(ctx: Context, url: str, sha: str) -> str:
    """The published formula with its source `url`, `sha256` and `homepage` set.

    `homepage` from the one `OWNER` constant, as `url` is (80's ruling on
    #348): the published formula still names the old owner there, and
    `brew info` shows it to users (policyforge-9b)."""
    # LF once, here: every pattern below anchors on "\n", and on a CRLF
    # formula the version line would silently not be added, failing step 8
    # exactly as #391 did (policyforge-b5 on #392; the live formula is LF).
    text = _base_formula(ctx).replace("\r\n", "\n")
    text = re.sub(
        r'^(\s*homepage ")[^"]+(")',
        rf"\g<1>{release_check.CANONICAL_HOMEPAGE}\g<2>",
        text,
        count=1,
        flags=re.M,
    )
    text = re.sub(r'^(\s*url ")[^"]+(")', rf"\g<1>{url}\g<2>", text, count=1, flags=re.M)
    # A commit archive carries no version, so the formula declares one (#391).
    # Homebrew takes a formula's version from its url; from `v1.6.1.tar.gz`
    # that is 1.6.1, but from `archive/<sha>.tar.gz` there is none. Homebrew
    # 4.6 guessed one ("stable 3", from the SHA's last digit) and installed;
    # 7.0.6 refuses: "invalid attribute for formula ...: version (nil)"
    # (policyforge-9b, at the 1.6.1 cut). Only for a commit archive: beside a
    # tag url an explicit version is one `brew audit --strict` calls redundant.
    text = re.sub(r'^\s*version "[^"]*"\n', "", text, flags=re.M)
    if _COMMIT_ARCHIVE_RE.search(url):
        text = re.sub(
            r'^(\s*url "[^"]+"\n)', rf'\g<1>  version "{ctx.version}"\n', text, count=1, flags=re.M
        )
    return re.sub(r'^(  sha256 ")[0-9a-f]{64}(")', rf"\g<1>{sha}\g<2>", text, count=1, flags=re.M)


#: A GitHub archive of a commit, not of a tag: `/archive/<40 hex>.tar.gz`.
_COMMIT_ARCHIVE_RE = re.compile(r"/archive/[0-9a-f]{40}\.tar\.gz$")


def _head_archive(ctx: Context) -> str:
    """The archive of the cut commit, which is the release PR's head."""
    sha = ctx.git("rev-parse", "HEAD")
    return f"https://github.com/{release_check.REPOSITORY}/archive/{sha}.tar.gz"


#: The install record, a tracking-issue comment's LAST line, as the other
#: artefact gates' records are: which commit was installed, for which
#: release, and how it went. Persistent because the script exits at the
#: user's approval (5) and is re-run after it, and the tag needs to know.
INSTALL_LINE = re.compile(
    r"^Release-install: ([0-9a-f]{40}) release=(\S+) result=(passed|FAILED|did-not-run|refused)\s*$"
)


def _install_record(ctx: Context) -> tuple[str, str]:
    """(sha, result) of the LATEST install record for this release, or ("", "")."""
    found = [
        (created, position, match.group(1), match.group(3))
        for created, position, line in _tracking_records(ctx)
        if (match := INSTALL_LINE.match(line)) and match.group(2) == ctx.version
    ]
    if not found:
        return "", ""
    _, _, sha, result = max(found)
    return sha, result


def _head_installed(ctx: Context) -> Check:
    """The release PR's head passed a clean-container install, and is still
    the head (#381, the user's "Install first").

    **The installed SHA comes from the install record, never from a fetch
    at the moment of checking** (the charge's --match-head-commit rule): it
    is compared with the PR's head as it is now and with the cut commit
    this script made. If the head moved after the install, the install is
    of a commit nobody is being asked to approve, so it is STALE.
    """
    if not ctx.tracking:
        return Check(False, ["no --tracking-issue given, so there is no install record to read"])
    sha, result = _install_record(ctx)
    pr = _release_pr(ctx)
    head = pr.get("headRefOid", "") if pr else ""
    cut = ctx.git("rev-parse", "HEAD")
    measured = [
        f"install record for {ctx.version} on #{ctx.tracking}: "
        f"{sha[:12] or 'none'} {result or ''}".rstrip(),
        f"release PR head now {head[:12] or '-'}, cut commit {cut[:12] or '-'}",
    ]
    if sha and head and sha != head:
        measured.append(
            f"STALE: the install was of {sha[:12]}, and the PR head is now {head[:12]}; "
            "whatever moved the head must be installed before anyone is asked to approve it"
        )
    measured += _ignored(ctx, INSTALL_LINE)
    return Check(bool(sha) and result == "passed" and sha == head == cut, measured)


def _install_head(ctx: Context) -> None:
    """Install the cut commit's archive, then post the record on the tracking
    issue, where the user reads it before approving the main merge."""
    sha = ctx.git("rev-parse", "HEAD")
    url = _head_archive(ctx)
    _install(ctx, url, "head install")
    said = ctx.notes.get("head install", "did not run")
    result = {"passed": "passed", "FAILED": "FAILED", "did not run": "did-not-run"}.get(
        said, "refused"
    )
    body = (
        f"Container install of the {ctx.version} release PR head `{sha}` "
        f"({url}), by `scripts/release.py`: **{said}**.\n\n"
        f"Release-install: {sha} release={ctx.version} result={result}"
    )
    posted = ctx.run(
        [
            "gh",
            "api",
            f"repos/{release_check.REPOSITORY}/issues/{ctx.tracking}/comments",
            "-f",
            f"body={body}",
        ]
    )
    if posted.returncode != 0:
        ctx.notes["head install"] = f"{said}, but the record was not posted to #{ctx.tracking}"


def _tag_archive(ctx: Context) -> str:
    return f"https://github.com/{release_check.REPOSITORY}/archive/refs/tags/{ctx.tag}.tar.gz"


def _install_check(ctx: Context, url: str, note: str) -> Check:
    if ctx.notes.get(note):
        return Check(ctx.notes[note] == "passed", [f"{note}: {ctx.notes[note]}"])
    return Check(False, [f"{note}: not yet run"])


def _all(*checks: Check) -> Check:
    """Several checks as one gate: every value printed, all must hold."""
    return Check(all(c.ok for c in checks), [line for c in checks for line in c.measured])


def _head_install_ready(ctx: Context) -> Check:
    """Before installing: a record to write to, the PR open AT the cut commit
    (not at something pushed after it), and its archive served."""
    pr = _release_pr(ctx)
    head = pr.get("headRefOid", "") if pr else ""
    cut = ctx.git("rev-parse", "HEAD")
    return _all(
        Check(
            bool(ctx.tracking),
            [f"tracking issue: {'#' + str(ctx.tracking) if ctx.tracking else 'none'}"],
        ),
        Check(
            bool(pr) and pr.get("state") == "OPEN" and head == cut,
            [
                f"release PR {'#' + str(pr['number']) if pr else 'none'} head {head[:12] or '-'} "
                f"is the cut commit {cut[:12]}: {head == cut}"
            ],
        ),
        _archive_served(_head_archive)(ctx),
    )


def _install(ctx: Context, url: str, note: str) -> None:
    formula = _formula(ctx, url, ctx.hash_url(url))
    if not release_check.names_canonical_owner(release_check.source_url_in_formula(formula)):
        ctx.notes[note] = "refused: the formula's url does not name the canonical owner"
        return
    if not release_check.names_canonical_homepage(release_check.homepage_in_formula(formula)):
        ctx.notes[note] = "refused: the formula's homepage does not name the canonical owner"
        return
    ran, ok, lines = ctx.install(formula, ctx.version)
    for line in lines[-6:]:
        print(f"      | {line}")
    ctx.notes[note] = "passed" if ran and ok else ("did not run" if not ran else "FAILED")
    if note == "candidate install":
        ctx.notes["candidate_formula"] = formula


def _archive_served(url_of: Callable[[Context], str]) -> Callable[[Context], Check]:
    def gate(ctx: Context) -> Check:
        url = url_of(ctx)
        status = ctx.status_of(url)
        return Check(status == 200, [f"{url} -> HTTP {status} (must be 200)"])

    return gate


def _tagged(ctx: Context) -> Check:
    remote = (
        ctx.run(
            ["git", "-C", str(ctx.root), "ls-remote", "--tags", "origin", f"{ctx.tag}^{{}}"]
        ).stdout
        or ""
    ).split()
    target = remote[0] if remote else ""
    release = (
        ctx.run(
            [
                "gh",
                "release",
                "view",
                ctx.tag,
                "--repo",
                release_check.REPOSITORY,
                "--json",
                "tagName",
            ]
        ).returncode
        == 0
    )
    main = ctx.notes.get("main_sha", "")
    return Check(
        bool(target) and target == main and release,
        [
            f"tag {ctx.tag} -> {target[:12] or '-'} "
            f"(must be main's merge commit {main[:12] or '?'})",
            f"GitHub Release {ctx.tag}: {'exists' if release else 'absent'}",
        ],
    )


def _tag(ctx: Context) -> None:
    main = ctx.notes["main_sha"]
    notes_file = Path(tempfile.mkdtemp()) / "notes.md"
    text = (ctx.root / "CHANGELOG.md").read_text(encoding="utf-8")
    section = re.search(rf"^## {re.escape(ctx.version)}\n(.*?)(?=^## |\Z)", text, re.M | re.S)
    notes_file.write_text(section.group(1).strip() if section else "", encoding="utf-8")
    ctx.run(
        ["git", "-C", str(ctx.root), "tag", "-a", ctx.tag, main, "-m", f"Release {ctx.version}"]
    )
    ctx.run(["git", "-C", str(ctx.root), "push", "origin", ctx.tag])
    ctx.run(
        [
            "gh",
            "release",
            "create",
            ctx.tag,
            "--repo",
            release_check.REPOSITORY,
            "--title",
            ctx.tag,
            "--notes-file",
            str(notes_file),
            "--verify-tag",
        ]
    )


def _resources_match_lock(ctx: Context) -> Check:
    """The lock decides (CONTRIBUTING): every formula resource pinned as the lock pins it.

    **Checked before the cut is written, not after the tag** (#389).
    `_formula` rewrites only `url`, `sha256`, `homepage` and `version`, so
    every install this script runs uses the base formula's resource pins.
    Checked after the tag, a runtime-dependency change would have been
    installed against the previous release's pins, approved, and tagged
    before anything said so. It sits before `changelog`, so a mismatch
    refuses before the release PR exists (policyforge-ba on #419).

    What is read is the base formula, `--formula` if given, else the
    published one (`_base_formula`), or the candidate once one exists,
    which carries the same pins. The output names which."""
    formula = ctx.notes.get("candidate_formula") or _base_formula(ctx)
    source = (
        "the candidate formula"
        if ctx.notes.get("candidate_formula")
        else (f"--formula {ctx.formula_path}" if ctx.formula_path else "the published formula")
    )
    have = release_check.formula_resources(formula)
    pins = release_check.lock_pins((ctx.root / release_check.LOCK).read_text(encoding="utf-8"))
    mismatched = sorted(n for n in set(have) & set(pins) if have[n] != pins[n])
    unlocked = sorted(set(have) - set(pins))
    return Check(
        bool(have) and not mismatched and not unlocked,
        [
            f"formula resources {len(have)} (must be > 0), lock pins {len(pins)}",
            f"read from {source}",
            f"version mismatches with {release_check.LOCK}: {mismatched or 'none'}",
            f"in the formula and in no lock: {unlocked or 'none'}",
            *(
                []
                if not (mismatched or unlocked)
                else [
                    "regenerate the formula's resource stanzas from the lock before cutting: "
                    "the install would otherwise test pins nobody is releasing (#389). "
                    "Run `brew update-python-resources`, reconcile every resource to the "
                    "lock (CONTRIBUTING), and pass that file with --formula PATH"
                ]
            ),
        ],
    )


TAP_URL = f"https://github.com/{TAP_REPOSITORY}.git"


def _published(ctx: Context) -> Check:
    """Did the push land: the tap's main, asked of the server, holds the candidate.

    Read through the contents API at the tip `ls-remote` names, never
    raw.githubusercontent.com: in the 1.6.1 cut raw served the 1.6.0 file
    for about 300 seconds after a correct push, and this postcondition
    failed on it (#416). Raw is the route a user's `brew` takes, so it
    belongs to step 14, which asks that question."""
    formula = ctx.notes.get("candidate_formula", "")
    if not formula:
        return Check(False, ["no candidate formula has passed its install in this run"])
    lines = []
    refused = ctx.notes.get("publish", "")
    if refused:
        lines.append(f"publish: {refused}")
    tip = _remote_tip(ctx, TAP_URL, "main")
    if not tip:
        return Check(False, [*lines, f"{TAP_REPOSITORY} main: no answer from ls-remote"])
    lines.append(f"{TAP_REPOSITORY} main is {tip[:12]} (ls-remote)")
    pushed = ctx.notes.get("tap_sha", "")
    if pushed:
        lines.append(f"that is the commit this run pushed ({pushed[:12]}): {tip == pushed}")
    read = ctx.run(
        [
            "gh",
            "api",
            "-H",
            "Accept: application/vnd.github.raw",
            f"repos/{TAP_REPOSITORY}/contents/{TAP_FORMULA_PATH}?ref={tip}",
        ]
    )
    if read.returncode != 0:
        return Check(False, [*lines, f"contents API at {tip[:12]}: exit {read.returncode}"])
    live = read.stdout or ""
    same = hashlib.sha256(live.encode()).hexdigest() == hashlib.sha256(formula.encode()).hexdigest()
    lines.append(f"formula at {tip[:12]} == the candidate that passed its install: {same}")
    return Check(same and not refused, lines)


def _publish(ctx: Context) -> None:
    """Clone the tap, commit the candidate, push; stop at the first failure.

    In the 1.6.1 cut `git commit` exited 128 (no identity on the machine),
    `git push` then said "Everything up-to-date" and exited 0, and nothing
    here read either status (#407). Every exit code is now read, the
    refusal is left in `notes` for the postcondition to print, and the
    commit takes its identity from this repository's git config, passed to
    that one process, rather than from whatever the machine has."""
    formula = ctx.notes["candidate_formula"]
    ctx.notes.pop("publish", None)
    name, email = ctx.git("config", "user.name"), ctx.git("config", "user.email")
    if not (name and email):
        ctx.notes["publish"] = (
            f"refused: no user.name/user.email in {ctx.root}'s git config to commit "
            "the tap as; nothing was cloned or pushed"
        )
        return
    work = Path(tempfile.mkdtemp())

    def ran(argv: list[str]) -> bool:
        done = ctx.run(argv)
        if done.returncode == 0:
            return True
        said = ((done.stderr or "").strip().splitlines() or ["(no stderr)"])[-1]
        ctx.notes["publish"] = (
            f"refused: `{' '.join(argv)}` exited {done.returncode} ({said}); nothing after it ran"
        )
        return False

    if not ran(["git", "clone", "-q", TAP_URL, str(work)]):
        return
    (work / TAP_FORMULA_PATH).write_text(formula, encoding="utf-8", newline="\n")
    identity = ["-c", f"user.name={name}", "-c", f"user.email={email}"]
    if not ran(["git", "-C", str(work), *identity, "commit", "-qam", f"policyforge {ctx.version}"]):
        return
    head = ctx.run(["git", "-C", str(work), "rev-parse", "HEAD"])
    ctx.notes["tap_sha"] = (head.stdout or "").strip() if head.returncode == 0 else ""
    ran(["git", "-C", str(work), "push", "-q", "origin", "HEAD:main"])


def _release_check_passes(ctx: Context) -> Check:
    code = ctx.run(_release_check_argv(ctx)).returncode
    return Check(code == 0, [f"release_check.py --version {ctx.version}: exit {code} (must be 0)"])


def _release_check_argv(ctx: Context) -> list[str]:
    # `--version`, not a positional: the 1.6.1 cut passed it positionally,
    # argparse exited 2 on the usage error, and the final check never ran
    # (#415). The test parses this argv with release_check's own parser.
    return [
        sys.executable,
        str(ctx.root / "scripts" / "release_check.py"),
        "--version",
        ctx.version,
    ]


# --- the two artefact gates (80's ruling on #348) ------------------------------
#
# The script cannot do the #226 re-measure or the post-zero review, but it can
# refuse to pass until each has left an ARTEFACT. Both are read from the
# release's tracking issue (`--tracking-issue N`), each as the LAST non-empty
# line of a comment -- the verdict-line rule, so quoting one in a discussion
# does not create one. Every session posts as the same GitHub account, so the
# handle in the line is the identity, as it is for `reviewer=`. `--execute`
# cannot satisfy either; only the comment can.

#: One per reviewer, posted after the milestone reached zero (CLAUDE.md,
#: "Closing a release train": product, research and quality each review).
REVIEW_LINE = re.compile(r"^Post-zero-review: (\S+) reviewer=policyforge-(\w+)\s*$")
POST_ZERO_REVIEWERS = ("80", "5b", "1d")

#: The #226 re-measure of every figure in the notes, naming the train SHA it
#: was done at. It must be the current train tip: a figure is a fact about a
#: moment, and only one taken after the last merge may ship.
MEASURE_LINE = re.compile(
    r"^Notes-measured-SHA: ([0-9a-f]{40}) release=(\S+) reviewer=policyforge-(\w+)\s*$"
)


#: The GitHub logins whose comments on the tracking issue count as records
#: (80's ruling on #383): the account every session posts as, and the user's.
#: By LOGIN, an identity, not by `author_association`, which is a role any
#: future collaborator would hold. The repository is public: without this,
#: a stranger's later "Release-install: <head> release=X result=passed"
#: overrode a real FAILED and opened the approval wait and the tag
#: (policyforge-ba and policyforge-b5 on #383, separately).
RECORD_AUTHORS = frozenset({"rdazzlebot", "rdazzleman"})


def _tracking_records(ctx: Context) -> list[tuple[str, int, str]]:
    """(created_at, position, last non-empty line) for every comment on the
    tracking issue by a `RECORD_AUTHORS` login, in the order GitHub lists them.

    `position` breaks a same-second tie by comment order, never by the line's
    text, which put "passed" after "FAILED" (ba on #383). Comments by anyone
    else are not records: they are ignored, and kept in `ctx.notes` so each
    gate can say it ignored them (`_ignored`)."""
    if not ctx.tracking:
        return []
    out = ctx.run(
        [
            "gh",
            "api",
            "--paginate",
            f"repos/{release_check.REPOSITORY}/issues/{ctx.tracking}/comments",
            "--jq",
            ".[] | [.created_at, .body, .user.login] | @json",
        ]
    ).stdout
    records: list[tuple[str, int, str]] = []
    ignored: list[list[str]] = []
    for position, line in enumerate((out or "").splitlines()):
        try:
            created, body, login = json.loads(line)
        except ValueError:
            continue
        lines = [x.strip() for x in (body or "").splitlines() if x.strip()]
        if not lines:
            continue
        if login in RECORD_AUTHORS:
            records.append((created, position, lines[-1]))
        else:
            ignored.append([str(login), lines[-1]])
    ctx.notes["ignored records"] = json.dumps(ignored)
    return records


def _ignored(ctx: Context, pattern: re.Pattern[str]) -> list[str]:
    """A measured line for each record-shaped line `pattern` matches that was
    posted by someone outside `RECORD_AUTHORS`: said, not silently dropped."""
    ignored = json.loads(ctx.notes.get("ignored records") or "[]")
    return [
        f"IGNORED a record by {login} (not in {sorted(RECORD_AUTHORS)}): {line[:80]}"
        for login, line in ignored
        if pattern.match(line)
    ]


def _milestone_zero_at(ctx: Context) -> str:
    """When the milestone reached zero: the latest `closed_at` among its issues."""
    repo = release_check.REPOSITORY
    milestones = ctx.run(["gh", "api", f"repos/{repo}/milestones?state=all&per_page=100"]).stdout
    number = next(
        (m["number"] for m in json.loads(milestones or "[]") if m.get("title") == ctx.version),
        None,
    )
    if number is None:
        return ""
    out = ctx.run(
        [
            "gh",
            "api",
            "--paginate",
            f"repos/{repo}/issues?milestone={number}&state=closed&per_page=100",
            "--jq",
            ".[] | select(.pull_request|not) | .closed_at",
        ]
    ).stdout
    stamps = [s.strip() for s in (out or "").splitlines() if s.strip()]
    return max(stamps) if stamps else ""


def _post_zero_reviewed(ctx: Context) -> Check:
    if not ctx.tracking:
        return Check(False, ["no --tracking-issue given, so there is no record to read"])
    zero_at = _milestone_zero_at(ctx)
    after = {
        match.group(2)
        for created, _position, line in _tracking_records(ctx)
        if (match := REVIEW_LINE.match(line))
        and match.group(1) == ctx.version
        and zero_at
        and created > zero_at
    }
    missing = [h for h in POST_ZERO_REVIEWERS if h not in after]
    return Check(
        bool(zero_at) and not missing,
        [
            f"milestone {ctx.version} reached zero at {zero_at or '?'}",
            f"post-zero reviews on #{ctx.tracking} after it: {sorted(after) or 'none'}",
            f"missing (each posts `Post-zero-review: {ctx.version} reviewer=policyforge-<handle>` "
            f"as a comment's last line): {missing or 'none'}",
            *_ignored(ctx, REVIEW_LINE),
        ],
    )


def _notes_measured(ctx: Context) -> Check:
    if not ctx.tracking:
        return Check(False, ["no --tracking-issue given, so there is no record to read"])
    tip = _server_tip(ctx, f"{TRAIN_PREFIX}{ctx.version}")
    measured = [
        (created, position, match.group(1))
        for created, position, line in _tracking_records(ctx)
        if (match := MEASURE_LINE.match(line)) and match.group(2) == ctx.version
    ]
    latest = max(measured)[2] if measured else ""
    return Check(
        bool(tip) and latest == tip,
        [
            f"train tip origin/{TRAIN_PREFIX}{ctx.version} ON THE SERVER: {tip[:12] or '?'}",
            f"latest `Notes-measured-SHA:` for {ctx.version} on #{ctx.tracking}: "
            f"{latest[:12] or 'none'} "
            "(must be the tip: a measurement before the last merge may be stale)",
            *_ignored(ctx, MEASURE_LINE),
        ],
    )


def steps() -> list[Step]:
    """The cut, in order. The order is the point: nothing here is optional."""
    return [
        Step("train-final", "the train is the release", CHECK, _milestone_open, _milestone_open),
        Step(
            "clean-tree",
            "standing on the pushed train, nothing uncommitted",
            CHECK,
            _train_tree,
            _train_tree,
        ),
        Step(
            "post-zero-review",
            "80, 5b and 1d each reviewed after the milestone reached zero",
            CHECK,
            _post_zero_reviewed,
            _post_zero_reviewed,
        ),
        Step(
            "notes-measured",
            "the #226 re-measure names the current train tip",
            CHECK,
            _notes_measured,
            _notes_measured,
        ),
        Step(
            "resources",
            "the formula's resources are the lock's, before anything installs with them",
            CHECK,
            _resources_match_lock,
            _resources_match_lock,
        ),
        Step(
            "changelog",
            "assemble changelog.d/ into `## X.Y.Z`",
            ACT,
            _fragments_ready,
            _changelog_cut,
            _assemble,
            would="assemble the fragments into CHANGELOG.md and remove them",
            commits_to="release-pr",
        ),
        Step(
            "version",
            "bump pyproject and __version__ together",
            ACT,
            _bump_ready,
            _bumped,
            _bump,
            would="set both version strings",
            commits_to="release-pr",
        ),
        Step(
            "install-pins",
            "point every install pin at this release (#413)",
            ACT,
            _pins_ready,
            _pins_current,
            _repin,
            would="rewrite each `<owner>/policyforge@vX.Y.Z` in the docs to this release",
            commits_to="release-pr",
        ),
        Step(
            "release-pr",
            "the cut, as a PR against main",
            ACT,
            _pr_ready,
            _pr_open,
            _open_pr,
            outward=True,
            would="commit, push the cut branch and open a PR against main",
        ),
        Step(
            "head-install",
            "install the release PR's head in a clean container, before approval",
            ACT,
            _head_install_ready,
            _head_installed,
            _install_head,
            outward=True,
            would=(
                "build and install the release PR head's archive with Homebrew in a "
                "container, and post the result on the tracking issue"
            ),
        ),
        Step(
            "main",
            "the user merges the release PR, with the install result in hand",
            WAIT,
            lambda c: _all(_pr_still_open(c), _head_installed(c)),
            _main_merged,
            would="the user's approval and merge of the release PR in GitHub",
        ),
        Step(
            "tag",
            "tag main's merge commit and publish the GitHub Release",
            ACT,
            lambda c: _all(_head_installed(c), _no_tag(c)),
            _tagged,
            _tag,
            outward=True,
            would="create and push the tag, and publish the GitHub Release",
        ),
        Step(
            "candidate-install",
            "install the candidate formula, before publishing it",
            ACT,
            _archive_served(_tag_archive),
            lambda c: _install_check(c, _tag_archive(c), "candidate install"),
            lambda c: _install(c, _tag_archive(c), "candidate install"),
            would="build and install the tag's formula with Homebrew in a container",
        ),
        Step(
            "publish",
            "publish the formula to the tap",
            ACT,
            lambda c: Check(
                bool(c.notes.get("candidate_formula")), ["a candidate formula passed its install"]
            ),
            _published,
            _publish,
            outward=True,
            would=f"push the formula to {TAP_REPOSITORY}",
        ),
        Step(
            "release-check",
            "what a user installs is what was released",
            CHECK,
            _release_check_passes,
            _release_check_passes,
        ),
    ]


# --- real side effects -------------------------------------------------------


def _real_run(argv: list[str]) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            argv, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=3600
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return subprocess.CompletedProcess(argv, 127, "", str(error))


def _real_status(url: str) -> int:
    import urllib.error
    import urllib.request

    # https only, refused in code rather than only suppressed: urllib also
    # opens `file://`, and every URL here is a GitHub archive this script
    # built. The suppression sits on the offending line, as release_check's
    # does, because semgrep honours `nosemgrep` only there.
    if not url.startswith("https://"):
        return 0
    request = urllib.request.Request(url, method="HEAD")
    try:
        with urllib.request.urlopen(request, timeout=60) as response:  # nosec B310  # nosemgrep
            return response.status
    except urllib.error.HTTPError as error:
        return error.code
    except OSError:
        return 0


def _install_script(version: str) -> str:
    """The container's `&&` chain, ending with the installed package's version.

    **The version is the one check that reads the artefact itself**
    (policyforge-ba on #348): an install of the wrong commit passes every
    other line here. `policyforge --version` does not exist, so it asks the
    formula's virtualenv for `policyforge.__version__`, the string step 6
    bumps. `test "$(...)" = X` fails on a wrong version and on no output
    alike. PROBE MEASURED on #348 against the published 1.6.0 formula in this
    image, on its Homebrew 4.6.20: it read 1.6.0, the arm expecting 9.9.9
    failed. The chain now updates Homebrew first (#391), so it measures the
    Homebrew a user installs with, not the one the image happens to ship.
    """
    python = '"$(brew --prefix local/candidate/policyforge)/libexec/bin/python"'
    read = "import policyforge, sys; sys.stdout.write(policyforge.__version__)"
    return " && ".join(
        [
            # The Homebrew a user has, not the image's: `homebrew/brew:latest`
            # still ships 4.6.20, and whether a run auto-updated decided whether
            # a formula with no version installed or was refused (#391: 1d's
            # run stayed on 4.6.20 and passed, 9b's updated to 7.0.6 and failed).
            "brew update --quiet",
            'echo "HOMEBREW: $(brew --version | head -1)"',
            "brew tap-new --no-git local/candidate",
            "cp /candidate/policyforge.rb "
            '"$(brew --repository)/Library/Taps/local/homebrew-candidate/Formula/"',
            "brew install --build-from-source local/candidate/policyforge",
            "brew test local/candidate/policyforge",
            "brew audit --strict local/candidate/policyforge",
            "mkdir -p /tmp/pf",
            # release_check's pinned smoke test, not retyped: `frameworks` in an
            # empty directory exits 1 by design, so `init` must come first.
            *(
                command
                for name, command in release_check.INSTALL_STEPS
                if name in ("init", "frameworks")
            ),
            f'test "$({python} -c \'{read}\')" = "{version}"',
        ]
    )


def _real_install(formula: str, version: str) -> tuple[bool, bool, list[str]]:
    """Install a local formula in a clean container through a throwaway tap.

    **Measured on #255, not assumed:** in the `homebrew/brew` image
    (Homebrew 4.6.20), `brew install --formula /path/policyforge.rb` is
    refused with advice to `brew tap-new`, while the same file copied into a
    tap made with `brew tap-new --no-git local/candidate` resolves. So the
    formula goes into that throwaway tap. Same `&&` chain and the same
    could-it-start probe as `release_check.run_install_check`.
    """
    import shutil

    if shutil.which("docker") is None:
        return False, False, ["docker is not on PATH"]
    probe = _real_run(["docker", "run", "--rm", CONTAINER_IMAGE, "true"])
    if probe.returncode != 0:
        return False, False, [f"could not start {CONTAINER_IMAGE}"]
    work = Path(tempfile.mkdtemp())
    (work / "policyforge.rb").write_text(formula, encoding="utf-8", newline="\n")
    script = _install_script(version)
    proc = _real_run(
        [
            "docker",
            "run",
            "--rm",
            "-v",
            f"{work}:/candidate:ro",
            CONTAINER_IMAGE,
            "bash",
            "-lc",
            script,
        ]
    )
    lines = ((proc.stdout or "") + (proc.stderr or "")).strip().splitlines()[-12:]
    lines.append(f"docker exit status: {proc.returncode}")
    return True, proc.returncode == 0, lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("version", help="the version to cut, e.g. 1.6.1")
    parser.add_argument("--execute", action="store_true", help="act; without it, a dry run")
    parser.add_argument(
        "--tracking-issue",
        type=int,
        help="the issue holding the post-zero reviews and the notes re-measure",
    )
    parser.add_argument(
        "--formula",
        type=Path,
        help="the regenerated, lock-reconciled formula to cut from (default: the published one)",
    )
    args = parser.parse_args(argv)
    if args.formula is not None and not args.formula.is_file():
        parser.error(f"--formula {args.formula}: no such file")
    if not re.fullmatch(r"\d+\.\d+\.\d+", args.version):
        print(f"release: {args.version!r} is not X.Y.Z")
        return 2
    ctx = Context(
        version=args.version,
        run=_real_run,
        status_of=_real_status,
        hash_url=release_check.hash_of,
        install=_real_install,
        tracking=args.tracking_issue,
        formula_path=args.formula,
    )
    print(f"release {ctx.tag}: {'EXECUTE' if args.execute else 'DRY RUN (nothing will change)'}")
    plan = steps()
    if not args.execute:
        # The whole order first: a dry run stops at the first step that would
        # act, so without this it would never show what comes after (#381).
        print("\nThe cut, in order:")
        for index, step in enumerate(plan, 1):
            kind = step.kind + (", outward" if step.outward else "")
            print(f"  {index:>2}. {step.key}: {step.title} [{kind}]")
    return run_steps(plan, ctx, execute=args.execute)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
