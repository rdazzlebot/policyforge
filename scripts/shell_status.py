#!/usr/bin/env python3
"""Refuse committed shell that reports success for a command that failed.

WHY THIS EXISTS. `cmd | tail` takes its exit status from `tail`, so the
status of `cmd` is discarded. Written as `cmd | tail && action`, it reads as
sequencing and is a concatenation: the action runs whatever `cmd` returned.
#213 catalogued **seven instances in one day**, every one caught downstream
and none prevented at the moment of typing, and three of those were in
sessions that had the rule in front of them.

**The rule was already written down** — in the team charge, in
`docs/verifying-a-merge.md`, in four sessions' memory files. Restating it
produced no measured reduction, because a rule that must be recalled fires
when you are already being careful and `| tail` is what you type when you
are not.

WHAT IT FOUND ON THE DAY IT WAS WRITTEN. One line, and it was ours:

    .github/workflows/ci.yml:91
    run: git ls-files -z '*.md' | xargs -0 mdformat --check

Measured, in both directions, rather than argued:

    bash -e             'false | xargs -0 mdformat --check'  -> exit 0
    bash -e -o pipefail 'false | xargs -0 mdformat --check'  -> exit 1

So if `git ls-files` failed, **CI's markdown check passed having examined
nothing** — a green light the whole team had been reading as "markdown is
fine". GitHub's default shell is `bash -e` with no pipefail, and the only
`shell: bash` default in that file is on a different job.

THE SECOND PATH, WHICH PIPEFAIL DOES NOT CLOSE. Found by policyforge-9b
against the fix above, which is why it is here:

    mdformat --check      (no paths at all)  -> exit 0
      "No files have been passed in. Doing nothing."

`xargs` without `-r` runs the command once on empty input. If `git ls-files`
*succeeds* and matches nothing — a renamed directory, a pattern that stops
matching — the tool runs, checks zero files and exits 0. Nothing failed, so
pipefail never fires. **A check whose population can silently become empty
reports the absence of input as the absence of problems**, which is the same
defect `test_the_population_is_not_empty` guards in #214, one layer out.

Hence two rules, not one, and `EMPTY_INPUT_TOOLS` below is the second.

WHAT THIS DOES NOT DO, deliberately.

It does not lint the interactive shell. Nobody lints what a session types at
a prompt, and **three of #213's seven instances were exactly that.** This
reduces the committed surface; it does not close the class, which is why
#213 stays open rather than being closed by this.

It does not require `set -o pipefail` in documentation snippets. A snippet is
something a reader runs by hand and watches; a script is something that runs
unattended and is believed. Only the second kind gets the requirement.

It does not forbid pipes. `PIPEFAIL_EXEMPT` takes a site and a reason for a
pipeline whose status genuinely does not matter, **pinned by the text of the
line rather than by a line number**, so an exemption cannot silently widen to
cover a line that moved underneath it.

Usage:

    python scripts/shell_status.py            # check; non-zero on a finding
    python scripts/shell_status.py --list     # print the population it derived
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

#: Commands that consume a stream and whose own exit status is almost never
#: the question being asked. Piping INTO one of these discards the status of
#: whatever produced the stream.
#:
#: Deliberately a list of stream consumers rather than "any pipe": `a | b`
#: where `b` is the real work is a normal pipeline, and a rule that refused
#: every pipe would be turned off within a day.
STREAM_CONSUMERS = (
    "head",
    "tail",
    "grep",
    "sed",
    "awk",
    "jq",
    "cut",
    "sort",
    "uniq",
    "wc",
    "tee",
    "cat",
    "xargs",
)

#: Tools KNOWN to treat "no input" as success, used only to sharpen the
#: failure message. **Not the rule.**
#:
#: The first version of this file made the list the rule, and
#: policyforge-ba asked the right question: the property belongs to tools,
#: the set of tools with it is larger than any list, and it grows whenever
#: someone adds a linter to CI. Measured in this venv rather than argued:
#:
#:     mdformat   exit 0      ruff       exit 0
#:     semgrep    exit 0      pip-audit  exit 0
#:     pytest     exit 0      bandit     exit 2
#:
#: **Three of those were missing from the list**, so the enumeration was
#: already incomplete on the day it was written -- the class-versus-instance
#: failure, in the file whose job is to catch that shape.
#:
#: So the rule below is keyed on the CONSTRUCT instead, which is derivable:
#: `xargs` without `-r` runs its command once on empty input. That is a
#: property of `xargs`, true for every tool it will ever be handed, and it
#: is the actual mechanism. This tuple only lets the message say which tool
#: is known to exit 0, and being absent from it changes nothing.
EMPTY_INPUT_TOOLS = ("mdformat", "ruff", "black", "shellcheck", "semgrep", "pip-audit", "pytest")

#: `xargs` with no `-r`/`--no-run-if-empty`: runs the command even when the
#: incoming list is empty. This is the derivable half of the empty-input
#: rule and does not depend on knowing the tool.
_XARGS_RUNS_ON_EMPTY = re.compile(r"\|\s*xargs\b(?![^|]*(?:-r\b|--no-run-if-empty))")

_CONSUMERS = "|".join(STREAM_CONSUMERS)

#: A stream consumer whose status is then used to gate something else.
#: `cmd | tail -4 && push` is the shape; the `&&` is what turns a discarded
#: status into a wrong decision.
_SWALLOWED = re.compile(rf"\|\s*(?:{_CONSUMERS})\b[^|]*&&")

#: Any pipe into a stream consumer, used for the pipefail requirement.
_PIPES_TO_CONSUMER = re.compile(rf"\|\s*(?:{_CONSUMERS})\b")

_PIPEFAIL = re.compile(r"set\s+(?:-o\s+pipefail|-[a-zA-Z]*o[a-zA-Z]*\s+pipefail|-euo\s+pipefail)")

#: Exemptions, pinned by the line's own text. A reason is required: an
#: exemption with no reason is indistinguishable from an oversight, and the
#: next reader cannot tell whether removing it is safe.
#:
#: Empty today, and that is the honest state — the one real finding was
#: fixed rather than exempted. Kept because a guard with no way to say
#: "this one is fine" gets deleted the first time it is wrong.
PIPEFAIL_EXEMPT: dict[str, str] = {}


#: How a block says "I checked that the list was not empty". Kept as a set of
#: shapes rather than one, because the natural spelling differs between a
#: bash array and a `find -print -quit`, and a rule that accepts only the
#: spelling its author used is the class-versus-instance failure again.
_NON_EMPTY_ASSERTIONS = (
    re.compile(r"\$\{#\w+\[@\]\}"),  # bash array length
    re.compile(r"\bwc\s+-l\b[^\n]*\b(?:-eq|-gt|-ne|\[)"),
    re.compile(r"\bxargs\b[^\n]*(?:-r\b|--no-run-if-empty)"),
    re.compile(r"\bgrep\s+-q\b"),
)


def _asserts_non_empty(block: str) -> bool:
    """Does this block prove it had input before believing a clean result?

    `xargs -r` counts: it declines to run the tool at all on empty input, so
    the tool cannot report "nothing to do" as success.
    """
    return any(pattern.search(block) for pattern in _NON_EMPTY_ASSERTIONS)


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    text: str
    rule: str
    detail: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}  [{self.rule}]\n    {self.text.strip()}\n    {self.detail}"


@dataclass(frozen=True)
class Source:
    """A committed thing that a shell will execute."""

    path: str
    kind: str  # "script" | "workflow" | "doc"
    lines: list[tuple[int, str]]

    @property
    def requires_pipefail(self) -> bool:
        """A doc snippet is watched by a person; a script is believed."""
        return self.kind in ("script", "workflow")


def tracked(pattern: str) -> list[str]:
    out = subprocess.run(
        ["git", "ls-files", pattern],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )
    return [line for line in out.stdout.splitlines() if line.strip()]


def _workflow_run_blocks(path: str, text: str) -> list[Source]:
    """Every `run:` block in a workflow, with its real file line numbers.

    Parsed by indentation rather than with a YAML library on purpose: the
    line numbers have to survive into the failure message, and a YAML load
    discards them. The cost is that this sees a `run:` inside a string; the
    benefit is that a finding can be pasted into an editor and found.
    """
    sources: list[Source] = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        match = re.match(r"^(\s*)-?\s*run:\s*(\S.*)?$", lines[i])
        if not match:
            i += 1
            continue
        indent, inline = match.group(1), match.group(2)
        body: list[tuple[int, str]] = []
        if inline and inline not in ("|", ">", "|-", ">-"):
            body.append((i + 1, inline))
            i += 1
        else:
            i += 1
            while i < len(lines):
                line = lines[i]
                if line.strip() and not line.startswith(indent + " "):
                    break
                body.append((i + 1, line))
                i += 1
        if body:
            sources.append(Source(path=path, kind="workflow", lines=body))
    return sources


_FENCE = re.compile(r"^```\s*(bash|sh|shell|console)\s*$")


def _doc_shell_blocks(path: str, text: str) -> list[Source]:
    sources: list[Source] = []
    body: list[tuple[int, str]] = []
    inside = False
    for number, line in enumerate(text.splitlines(), 1):
        if not inside and _FENCE.match(line.strip()):
            inside, body = True, []
            continue
        if inside and line.strip().startswith("```"):
            if body:
                sources.append(Source(path=path, kind="doc", lines=body))
            inside = False
            continue
        if inside:
            body.append((number, line))
    return sources


#: A crude, independent signal that a kind OUGHT to yield sources, used only
#: to decide whether zero is suspicious. Deliberately not the block parsers
#: above: two derivations of one fact are what let them disagree, and a
#: census computed by the parser would agree with the parser by construction.
_SIGNALS = {
    # Matches at most ONCE per file: a script is one source, and the
    # census counts BLOCKS. `\S` would have counted every non-space
    # character as a block the moment a *.sh was committed -- latent,
    # because the repository has none today, and it would have reported
    # a forty-character script as forty missing blocks.
    "script": (("*.sh",), re.compile(r"\A\s*\S", re.S)),
    # Both extensions, matching `population()`. With only `*.yml` a
    # `.yaml` workflow is read by the parser and invisible to the census,
    # so the one file the census exists to notice could be the one it
    # cannot see.
    "workflow": (
        (".github/workflows/*.yml", ".github/workflows/*.yaml"),
        re.compile(r"^\s*-?\s*run:", re.M),
    ),
    "doc": (("*.md",), re.compile(r"^```[ \t]*(?:bash|sh|shell|console)[ \t]*$", re.M)),
}


def census() -> dict[str, dict[str, int]]:
    """How many files of each kind *look like* they should yield sources.

    **This is the second derivation, and it exists because of a real hole.**
    `main` originally refused only an entirely empty population, so breaking
    a single pathspec left the other kinds intact and the tool printed
    `clean` — while `ci.yml`, this lint's one real finding, went unexamined
    and exit was 0. Found by policyforge-9b by mutating one pathspec.

    **`0 script` is today's correct state**, since the repository has no
    committed `*.sh` files, so a bare "no kind may be zero" rule would be
    wrong on arrival. Hence a census: a kind may be zero only when nothing
    of that kind looks like it should have produced anything.

    **What this defends against is an EDITED PATHSPEC, not a renamed
    directory** — policyforge-9b's correction, and the distinction is not
    pedantic. GitHub reads workflows only from `.github/workflows/`, so
    renaming that directory means those files stop being workflows and
    reporting zero is *right* rather than blind. The plausible event is
    someone editing `population()` and not `_SIGNALS`, which is exactly
    what was measured.

    **The residual, so it is a known floor rather than a surprise.** The
    two derivations are independent in *method* but share a *pathspec
    prefix*, and they sit about forty lines apart. Point both at
    `.github/ci/*` and this reports `clean across 26 source(s)` and exits
    0, with five workflow files still tracked and unexamined — measured,
    not supposed. That takes two coordinated edits rather than one, so it
    is narrower than what the census catches, but it is not zero.
    **A second derivation raises the cost of going blind; it does not make
    it impossible.**
    """
    found: dict[str, dict[str, int]] = {}
    for kind, (patterns, signal) in _SIGNALS.items():
        hits: dict[str, int] = {}
        for pattern in patterns:
            for path in tracked(pattern):
                text = (REPO_ROOT / path).read_text(encoding="utf-8", errors="replace")
                blocks = len(signal.findall(text))
                if blocks:
                    hits[path] = blocks
        found[kind] = hits
    return found


def population() -> list[Source]:
    """Derive what a shell will execute, from the repository rather than a list.

    **Derived, not listed**, which is the difference between a guard that
    covers a new file and one that covers the files someone remembered. The
    non-empty assertion in `main` is the other half: a derivation that stops
    matching enumerates zero and every assertion over it becomes vacuous.
    """
    sources: list[Source] = []
    for path in tracked("*.sh"):
        text = (REPO_ROOT / path).read_text(encoding="utf-8", errors="replace")
        sources.append(
            Source(path=path, kind="script", lines=list(enumerate(text.splitlines(), 1)))
        )
    for path in tracked(".github/workflows/*.yml") + tracked(".github/workflows/*.yaml"):
        text = (REPO_ROOT / path).read_text(encoding="utf-8", errors="replace")
        sources.extend(_workflow_run_blocks(path, text))
    for path in tracked("*.md"):
        text = (REPO_ROOT / path).read_text(encoding="utf-8", errors="replace")
        sources.extend(_doc_shell_blocks(path, text))
    return sources


def _strip_comment(line: str) -> str:
    """Drop a trailing `#` comment so prose about a rule is not a violation.

    Written after two tests in this repository failed on their own
    explanation — a docstring naming the strings it asserts are absent. A
    checker that flags the comment describing it has the same defect.
    """
    out, quote = [], ""
    for char in line:
        if quote:
            out.append(char)
            if char == quote:
                quote = ""
            continue
        if char in "'\"":
            quote = char
            out.append(char)
            continue
        if char == "#":
            break
        out.append(char)
    return "".join(out)


def findings(sources: list[Source]) -> list[Finding]:
    results: list[Finding] = []
    for source in sources:
        text = "\n".join(line for _, line in source.lines)
        has_pipefail = bool(_PIPEFAIL.search(text))
        for number, raw in source.lines:
            line = _strip_comment(raw)
            if not line.strip():
                continue
            if _SWALLOWED.search(line):
                results.append(
                    Finding(
                        source.path,
                        number,
                        raw,
                        "swallowed-status",
                        "the `&&` runs whatever the left of the pipe returned; "
                        "capture first (`cmd > log 2>&1; rc=$?`) and branch on `$rc`.",
                    )
                )
            if not (source.requires_pipefail and _PIPES_TO_CONSUMER.search(line)):
                continue

            if not (has_pipefail or line.strip() in PIPEFAIL_EXEMPT):
                results.append(
                    Finding(
                        source.path,
                        number,
                        raw,
                        "no-pipefail",
                        "this pipeline's status comes from the right-hand command. "
                        "Add `set -o pipefail` to the block, or name it in "
                        "PIPEFAIL_EXEMPT with a reason.",
                    )
                )

            # **Deliberately NOT nested under the pipefail branch above, and
            # the first version of this file got that wrong.** Adding
            # `set -o pipefail` silenced this rule, which is precisely the
            # mistake it exists to prevent: the two failures are
            # independent, and the empty-input one survives the fix for the
            # other. The test that caught it is named after the property.
            # Keyed on the construct, not on a list of tool names: `xargs`
            # without `-r` runs its command once on empty input, whatever
            # that command is. Naming the tool only sharpens the message.
            if _XARGS_RUNS_ON_EMPTY.search(line) and not _asserts_non_empty(text):
                known = next(
                    (t for t in EMPTY_INPUT_TOOLS if re.search(rf"\b{re.escape(t)}\b", line)),
                    "",
                )
                because = (
                    f"`{known}` is known to exit 0 when given no paths, so "
                    if known
                    else "the command then runs with no paths, so "
                )
                results.append(
                    Finding(
                        source.path,
                        number,
                        raw,
                        "empty-input-passes",
                        "`xargs` without `-r` runs its command even when the list "
                        f"is empty. {because}an empty list reads as 'all clean'. "
                        "pipefail does not fire here -- nothing failed. Assert the "
                        "list is non-empty, or pass `xargs -r`.",
                    )
                )
    return results


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list", action="store_true", help="print the derived population")
    args = parser.parse_args(argv)

    sources = population()

    # The assertion that keeps every other assertion meaningful, and it is
    # **per kind, not over the union.**
    #
    # The first version asked only `if not sources`. A derivation over three
    # kinds has three ways to go vacuous and a union has one, so breaking a
    # single pathspec left the other kinds intact, printed `clean`, and
    # exited 0 -- with `ci.yml`, this lint's one real finding, unexamined.
    # Measured by policyforge-9b, confirmed here: the tool reported clean on
    # a tree that still contained the violation.
    #
    # `0 script` is today's CORRECT state (no committed *.sh), so the rule
    # cannot be "no kind may be zero". The census is an independent, cruder
    # derivation of "should this kind have produced anything", which is what
    # separates *nothing to find* from *stopped looking*. See `census()` for
    # what this does and does not defend against -- notably that a renamed
    # `.github/workflows/` is a legitimate zero, and that two coordinated
    # edits still defeat both derivations.
    # **Compared as SETS OF FILES, not as counts per kind.** The first
    # version compared `census()` against the parser per kind and fired
    # only when the parser produced zero of a kind, so a 56% loss of the
    # workflow population reported `clean` and exited 0 -- measured on the
    # train. The cause was not the comparison but the UNITS: the census
    # counted files (3 workflows) and the parser counted run-blocks (34),
    # and the only question answerable across those two numbers is whether
    # both are zero. Extent was unreachable by construction, not by
    # oversight. See #228.
    #
    # Naming the files rather than counting them puts both sides in the
    # same unit, and it needs no pinned bound: the population may grow
    # freely, and a file that stops being examined is named rather than
    # absorbed into a smaller total.
    #
    # **What this does NOT close, measured rather than reasoned about.**
    # policyforge-b5's formulation of #228 is that a shrink is invisible
    # *because* a check was made more specific -- so the same question
    # has to be asked of this fix. Asked and answered:
    #
    #     edit the parser pathspec only     before: exit 0, silent
    #                                        after: exit 2, names both files
    #     edit census AND parser pathspecs  before: exit 0
    #                                        after: exit 0      <- unchanged
    #
    # The one-edit case is closed; the coordinated two-edit case is not,
    # and is the residual `census()` already discloses. It is unchanged
    # by this, not introduced by it. Both derivations reach the tree
    # through a pathspec, so narrowing both in step defeats them both --
    # which is an argument for deriving from the whole tracked set and
    # classifying, so a narrowed spec moves files to "unclassified"
    # rather than out of existence. Not done here: one edit is the
    # accident-shaped case, two coordinated edits in the same direction
    # forty lines apart is not.
    # **Compared in BLOCKS, per file.** The previous version compared FILE
    # SETS -- census files minus produced files. That catches a file falling
    # out of the derivation entirely and is blind to a file producing FEWER
    # BLOCKS than it holds: capping run-blocks at one per file took the
    # population 34 -> 3, a 91% loss, every file still produced something,
    # so the set difference was empty and this exited 0 saying `clean`. A
    # real violation inside a dropped block was invisible, not merely
    # uncounted.
    #
    # Found by policyforge-9b; confirmed by policyforge-ba, who seeded a
    # real `| tail -4 && git push` inside a dropped block and watched it go
    # from exit 1 to exit 0.
    #
    # **The unit is the whole fix, and ba named the trap that was waiting
    # for me**: classifying FILES and counting BLOCKS reproduces this a
    # third time, and it would look like a remedy. Both sides count blocks.
    produced: dict[str, dict[str, int]] = {kind: {} for kind in _SIGNALS}
    for source in sources:
        produced[source.kind][source.path] = produced[source.kind].get(source.path, 0) + 1

    # A FLOOR rather than equality: the parser finding MORE than the crude
    # signal is not a shrink, and the danger has one direction. Measured on
    # this tree they agree exactly, file by file -- 15/15, 8/8, 11/11 across
    # the workflows -- so the floor is not slack hiding anything today.
    silent = {
        kind: rows
        for kind, rows in (
            (
                kind,
                sorted(
                    (path, blocks, produced[kind].get(path, 0))
                    for path, blocks in counts.items()
                    if produced[kind].get(path, 0) < blocks
                ),
            )
            for kind, counts in census().items()
        )
        if rows
    }
    if silent:
        for kind, rows in silent.items():
            missing = sum(blocks - got for _, blocks, got in rows)
            print(
                f"shell_status: {missing} {kind} block(s) went missing "
                f"across {len(rows)} file(s).\n"
                f"  That is not 'no problems'; it is a broken derivation\n"
                f"  -- a pathspec, or a block parser, that stopped matching.\n"
                f"  Each row is file, blocks signalled, blocks parsed:\n"
                + "\n".join(f"    {path}  {blocks} -> {got}" for path, blocks, got in rows),
                file=sys.stderr,
            )
        return 2
    if not sources:
        print(
            "shell_status: derived ZERO shell sources from this repository.\n"
            "  That is not 'no problems'; it is a broken derivation.",
            file=sys.stderr,
        )
        return 2

    if args.list:
        for source in sources:
            first = source.lines[0][0]
            print(f"  {source.kind:9} {source.path}:{first}  ({len(source.lines)} lines)")
        print(f"\n{len(sources)} shell source(s)")
        return 0

    results = findings(sources)
    if results:
        print(f"shell_status: {len(results)} finding(s)\n", file=sys.stderr)
        for finding in results:
            print(f"{finding}\n", file=sys.stderr)
        return 1

    scripts = sum(1 for s in sources if s.kind == "script")
    workflows = sum(1 for s in sources if s.kind == "workflow")
    docs = sum(1 for s in sources if s.kind == "doc")
    print(
        f"shell_status: clean across {len(sources)} source(s) "
        f"({scripts} script, {workflows} workflow run-block, {docs} doc block)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
