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
  stray invocation cannot cut a release.
- **The script never merges to main.** Final approval to main is the user's,
  in GitHub, and the ruleset makes it impossible anyway. That step is a WAIT:
  it reports what it is waiting for and exits 5, and a re-run after the
  user's merge continues.

TWO INSTALL TESTS (the user's ruling on #255, relayed by 80): the BRANCH
archive of main's merge commit is installed in a clean container before any
tag exists, then the CANDIDATE formula (the tag's archive) is installed
before it is published to the tap, and `release_check.py` checks the
PUBLISHED formula last.

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
    #: Installs a formula text in a clean container: (ran, ok, lines).
    install: Callable[[str], tuple[bool, bool, list[str]]] = None  # type: ignore[assignment]
    #: Reads the typed confirmation for an outward step.
    confirm: Callable[[str], str] = input
    #: The release's tracking issue, where the two artefact gates read their records.
    tracking: int | None = None
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

        if step.outward:
            typed = ctx.confirm(f"    type '{step.key}' to {step.would}: ").strip()
            if typed != step.key:
                out(f"    not confirmed (typed {typed!r}); stopping before {step.key}")
                return 6

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


def _train_tree(ctx: Context) -> Check:
    branch = ctx.git("rev-parse", "--abbrev-ref", "HEAD")
    head = ctx.git("rev-parse", "HEAD")
    remote = ctx.git("rev-parse", f"origin/{branch}") if branch.startswith(TRAIN_PREFIX) else ""
    cut = _release_pr(ctx).get("headRefOid", "")
    dirty = ctx.git("status", "--porcelain")
    ok = branch.startswith(TRAIN_PREFIX) and head in {remote, cut} - {""} and not dirty
    return Check(
        ok,
        [
            f"branch {branch!r} (must start {TRAIN_PREFIX!r})",
            f"HEAD {head[:12]}: origin/{branch} {remote[:12] or '-'}, "
            f"release PR head {cut[:12] or '-'} (must be one)",
            f"uncommitted changes: {len(dirty.splitlines())} (must be 0)",
        ],
    )


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
            "--search",
            f"Release {ctx.version} in:title",
            "--json",
            "number,state,headRefOid,mergeCommit,title",
        ]
    ).stdout
    prs = [
        p
        for p in json.loads(out or "[]")
        if p.get("title", "").startswith(f"Release {ctx.version}")
    ]
    return prs[0] if prs else {}


def _pr_ready(ctx: Context) -> Check:
    return Check(True, ["the cut commit will be pushed and a PR opened against main"])


def _pr_open(ctx: Context) -> Check:
    pr = _release_pr(ctx)
    head = ctx.git("rev-parse", "HEAD")
    ok = bool(pr) and (pr.get("state") == "MERGED" or pr.get("headRefOid") == head)
    return Check(
        ok, [f"release PR: {'#' + str(pr['number']) + ' ' + pr['state'] if pr else 'none'}"]
    )


def _open_pr(ctx: Context) -> None:
    branch = f"9b/release-{ctx.version}"
    ctx.run(["git", "-C", str(ctx.root), "commit", "-am", f"Release {ctx.version}"])
    ctx.run(["git", "-C", str(ctx.root), "push", "origin", f"HEAD:refs/heads/{branch}"])
    ctx.run(
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
        ]
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


def _formula(ctx: Context, url: str, sha: str) -> str:
    """The published formula with its source `url`, `sha256` and `homepage` set.

    `homepage` from the one `OWNER` constant, as `url` is (80's ruling on
    #348): the published formula still names the old owner there, and
    `brew info` shows it to users (policyforge-9b)."""
    text = release_check.fetch_formula()
    text = re.sub(
        r'^(\s*homepage ")[^"]+(")',
        rf"\g<1>{release_check.CANONICAL_HOMEPAGE}\g<2>",
        text,
        count=1,
        flags=re.M,
    )
    text = re.sub(r'^(\s*url ")[^"]+(")', rf"\g<1>{url}\g<2>", text, count=1, flags=re.M)
    return re.sub(r'^(  sha256 ")[0-9a-f]{64}(")', rf"\g<1>{sha}\g<2>", text, count=1, flags=re.M)


def _branch_archive(ctx: Context) -> str:
    sha = ctx.notes.get("main_sha", "")
    return f"https://github.com/{release_check.REPOSITORY}/archive/{sha}.tar.gz"


def _tag_archive(ctx: Context) -> str:
    return f"https://github.com/{release_check.REPOSITORY}/archive/refs/tags/{ctx.tag}.tar.gz"


def _install_check(ctx: Context, url: str, note: str) -> Check:
    if ctx.notes.get(note):
        return Check(ctx.notes[note] == "passed", [f"{note}: {ctx.notes[note]}"])
    return Check(False, [f"{note}: not yet run"])


def _branch_install_done(ctx: Context) -> Check:
    """Done if it passed in this run, or if the tag exists: the tag step's
    gate refuses to tag until a branch install has passed, so a tag is proof
    one did. Without the second half a re-run after tagging would stop here,
    since this step's own gate requires that no tag exists."""
    if not _no_tag(ctx).ok:
        return Check(True, [f"tag {ctx.tag} exists, so the pre-tag branch install passed"])
    return _install_check(ctx, _branch_archive(ctx), "branch install")


def _install(ctx: Context, url: str, note: str) -> None:
    formula = _formula(ctx, url, ctx.hash_url(url))
    if not release_check.names_canonical_owner(release_check.source_url_in_formula(formula)):
        ctx.notes[note] = "refused: the formula's url does not name the canonical owner"
        return
    if not release_check.names_canonical_homepage(release_check.homepage_in_formula(formula)):
        ctx.notes[note] = "refused: the formula's homepage does not name the canonical owner"
        return
    ran, ok, lines = ctx.install(formula)
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
    """The lock decides (CONTRIBUTING): every formula resource pinned as the lock pins it."""
    formula = ctx.notes.get("candidate_formula") or release_check.fetch_formula()
    have = release_check.formula_resources(formula)
    pins = release_check.lock_pins((ctx.root / release_check.LOCK).read_text(encoding="utf-8"))
    mismatched = sorted(n for n in set(have) & set(pins) if have[n] != pins[n])
    unlocked = sorted(set(have) - set(pins))
    return Check(
        bool(have) and not mismatched and not unlocked,
        [
            f"formula resources {len(have)} (must be > 0), lock pins {len(pins)}",
            f"version mismatches with {release_check.LOCK}: {mismatched or 'none'}",
            f"in the formula and in no lock: {unlocked or 'none'}",
        ],
    )


def _published(ctx: Context) -> Check:
    formula = ctx.notes.get("candidate_formula", "")
    if not formula:
        return Check(False, ["no candidate formula has passed its install in this run"])
    live = release_check.fetch_formula()
    same = hashlib.sha256(live.encode()).hexdigest() == hashlib.sha256(formula.encode()).hexdigest()
    return Check(same, [f"published formula == the candidate that passed its install: {same}"])


def _publish(ctx: Context) -> None:
    formula = ctx.notes["candidate_formula"]
    work = Path(tempfile.mkdtemp())
    ctx.run(["git", "clone", "-q", f"https://github.com/{TAP_REPOSITORY}.git", str(work)])
    (work / TAP_FORMULA_PATH).write_text(formula, encoding="utf-8", newline="\n")
    ctx.run(["git", "-C", str(work), "commit", "-qam", f"policyforge {ctx.version}"])
    ctx.run(["git", "-C", str(work), "push", "-q", "origin", "HEAD:main"])


def _release_check_passes(ctx: Context) -> Check:
    code = ctx.run(
        [sys.executable, str(ctx.root / "scripts" / "release_check.py"), ctx.version]
    ).returncode
    return Check(code == 0, [f"release_check.py {ctx.version}: exit {code} (must be 0)"])


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


def _tracking_records(ctx: Context) -> list[tuple[str, str]]:
    """(created_at, last non-empty line) for every comment on the tracking issue."""
    if not ctx.tracking:
        return []
    out = ctx.run(
        [
            "gh",
            "api",
            "--paginate",
            f"repos/{release_check.REPOSITORY}/issues/{ctx.tracking}/comments",
            "--jq",
            ".[] | [.created_at, .body] | @json",
        ]
    ).stdout
    records = []
    for line in (out or "").splitlines():
        try:
            created, body = json.loads(line)
        except ValueError:
            continue
        lines = [x.strip() for x in (body or "").splitlines() if x.strip()]
        if lines:
            records.append((created, lines[-1]))
    return records


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
        for created, line in _tracking_records(ctx)
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
        ],
    )


def _notes_measured(ctx: Context) -> Check:
    if not ctx.tracking:
        return Check(False, ["no --tracking-issue given, so there is no record to read"])
    tip = ctx.git("rev-parse", f"origin/{TRAIN_PREFIX}{ctx.version}")
    measured = [
        (created, match.group(1))
        for created, line in _tracking_records(ctx)
        if (match := MEASURE_LINE.match(line)) and match.group(2) == ctx.version
    ]
    latest = max(measured)[1] if measured else ""
    return Check(
        bool(tip) and latest == tip,
        [
            f"train tip origin/{TRAIN_PREFIX}{ctx.version}: {tip[:12] or '?'}",
            f"latest `Notes-measured-SHA:` for {ctx.version} on #{ctx.tracking}: "
            f"{latest[:12] or 'none'} "
            "(must be the tip: a measurement before the last merge may be stale)",
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
            "changelog",
            "assemble changelog.d/ into `## X.Y.Z`",
            ACT,
            _fragments_ready,
            _changelog_cut,
            _assemble,
            would="assemble the fragments into CHANGELOG.md and remove them",
        ),
        Step(
            "version",
            "bump pyproject and __version__ together",
            ACT,
            _bump_ready,
            _bumped,
            _bump,
            would="set both version strings",
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
            "main",
            "the user merges the release PR",
            WAIT,
            lambda c: Check(True),
            _main_merged,
            would="the user's approval and merge of the release PR in GitHub",
        ),
        Step(
            "branch-install",
            "install main's merge commit in a clean container, before any tag",
            ACT,
            lambda c: Check(
                _no_tag(c).ok and _archive_served(_branch_archive)(c).ok,
                _no_tag(c).measured + _archive_served(_branch_archive)(c).measured,
            ),
            _branch_install_done,
            lambda c: _install(c, _branch_archive(c), "branch install"),
            would="build and install the branch archive with Homebrew in a container",
        ),
        Step(
            "tag",
            "tag main's merge commit and publish the GitHub Release",
            ACT,
            lambda c: Check(
                _install_check(c, "", "branch install").ok and _no_tag(c).ok,
                _install_check(c, "", "branch install").measured + _no_tag(c).measured,
            ),
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
            "resources",
            "the formula's resources are the lock's",
            CHECK,
            _resources_match_lock,
            _resources_match_lock,
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


def _real_install(formula: str) -> tuple[bool, bool, list[str]]:
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
    script = " && ".join(
        [
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
        ]
    )
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
    args = parser.parse_args(argv)
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
    )
    print(f"release {ctx.tag}: {'EXECUTE' if args.execute else 'DRY RUN (nothing will change)'}")
    return run_steps(steps(), ctx, execute=args.execute)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
