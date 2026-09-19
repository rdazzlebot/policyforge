#!/usr/bin/env python3
"""Run the full quality-check suite locally, in one command.

Runs the same checks enforced in .pre-commit-config.yaml and
.github/workflows/ci.yml: ruff (lint + format), pytest, bandit (static
security analysis), semgrep (broader SAST — catches patterns bandit's
Python-specific ruleset doesn't, e.g. GitHub Actions supply-chain hygiene),
pip-audit (dependency CVEs), mdformat (markdown quality), and gitleaks
(secrets scan, if installed).

Ruff's rule selection, line length and per-file ignores live in
pyproject.toml, so this script, the pre-commit hook and CI all enforce
exactly the same thing instead of drifting apart.

Each check is invoked directly rather than through
`pre-commit run` so this has no dependency on pre-commit's hook-environment
builds — notably, pre-commit's official gitleaks hook builds gitleaks from
source via Go on first run, which requires outbound access to Go's module
proxy (proxy.golang.org) and can fail on restrictive corporate networks
even though nothing is actually wrong with your setup. GitHub Actions CI
doesn't have this issue (see ci.yml, which uses the gitleaks-action
directly) — this script's gitleaks check is a local convenience, not the
only place it runs.

Usage:
    python scripts/check.py

Requires: pip install -e ".[dev]"

semgrep is not in the dev extra: it pins its own dependencies exactly, and
installed beside the project those pins became the project's. It is found on
PATH or in `.tools/semgrep`, built from its own hashed lock:

    python -m venv .tools/semgrep
    .tools/semgrep/Scripts/pip install --require-hashes -r requirements/semgrep/semgrep.txt

(`bin/` rather than `Scripts/` outside Windows). Without it, that check is
skipped with a note, as gitleaks is.

Optional: install the gitleaks binary to get the secrets scan locally too
(Windows: `winget install gitleaks.gitleaks`; otherwise download from
https://github.com/gitleaks/gitleaks/releases). Without it, that one check
is skipped with a note, not silently ignored.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

import tree_guard

REPO_ROOT = Path(__file__).resolve().parent.parent

# Checks that can decline to run, and the `--allow-skip` name for each.
# Written out rather than derived from the label, because deriving a key by
# splitting a display string is how you get two checks silently sharing one
# name. A check that returns None without an entry here stops the script.
SKIP_FLAGS = {
    "semgrep (broader SAST)": "semgrep",
    "gitleaks (secrets scan)": "gitleaks",
}


def run(label: str, cmd: list[str]) -> bool:
    print(f"\n{'=' * 60}\n{label}\n{'=' * 60}")
    result = subprocess.run(cmd, cwd=REPO_ROOT)
    return result.returncode == 0


def check_gitleaks() -> bool | None:
    """True/False if it ran, None if skipped (binary not installed)."""
    if shutil.which("gitleaks") is None:
        print(
            f"\n{'=' * 60}\ngitleaks (secrets scan)\n{'=' * 60}\n"
            "SKIPPED — gitleaks binary not found on PATH.\n"
            "Install it once (Windows: `winget install gitleaks.gitleaks`, "
            "or grab a release from "
            "https://github.com/gitleaks/gitleaks/releases), then re-run "
            "this script. CI runs this check regardless (see "
            ".github/workflows/ci.yml) — this is just for a fast local "
            "check before you push."
        )
        return None
    return run(
        "gitleaks (secrets scan)",
        ["gitleaks", "detect", "--source", str(REPO_ROOT), "--verbose", "--redact"],
    )


def find_semgrep() -> str | None:
    """semgrep on PATH, else the `.tools/semgrep` environment, else None."""
    on_path = shutil.which("semgrep")
    if on_path:
        return on_path
    for scripts in ("Scripts", "bin"):
        found = shutil.which("semgrep", path=str(REPO_ROOT / ".tools" / "semgrep" / scripts))
        if found:
            return found
    return None


def check_semgrep() -> bool | None:
    """True/False if it ran, None if skipped (semgrep not installed)."""
    semgrep = find_semgrep()
    if semgrep is None:
        print(
            f"\n{'=' * 60}\nsemgrep (broader SAST)\n{'=' * 60}\n"
            "SKIPPED — semgrep not found on PATH or in .tools/semgrep.\n"
            "It has its own lock, kept out of the dev extra. Install it once:\n"
            "  python -m venv .tools/semgrep\n"
            "  .tools/semgrep/Scripts/pip install --require-hashes "
            "-r requirements/semgrep/semgrep.txt\n"
            "(bin/ instead of Scripts/ outside Windows), then re-run this "
            "script. CI runs this check regardless."
        )
        return None
    return run(
        "semgrep",
        [
            semgrep,
            "scan",
            "--config=p/python",
            "--config=p/security-audit",
            "--config=p/owasp-top-ten",
            "--error",
            ".",
        ],
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the full quality-check suite locally, in one command."
    )
    parser.add_argument(
        "--allow-skip",
        action="append",
        default=[],
        choices=sorted(set(SKIP_FLAGS.values())),
        metavar="TOOL",
        help=(
            "Accept that this tool is missing and let the gate still pass. "
            "Repeatable. Without it, a check that did not run fails the gate."
        ),
    )
    allow_skip = set(parser.parse_args(argv).allow_skip)

    # Before anything runs: the `policyforge` every check below would import
    # has to be this tree's. In a git worktree it is not — the editable
    # install pins the checkout it was made from — and the whole gate would
    # report on code it never loaded. Refused, with the fix, rather than
    # passed quietly (see scripts/tree_guard.py).
    refusal = tree_guard.foreign_source(
        tree_guard.resolved_origin(), REPO_ROOT, invocation="python scripts/check.py"
    )
    if refusal:
        print(refusal, file=sys.stderr)
        return 2

    # Every markdown file the pre-commit mdformat hook would touch, so this
    # script and that hook can't disagree about what "formatted" means. Only
    # output/ is excluded — it holds generated drafts, which are checked by
    # `check_markdown_quality` at generation time instead.
    md_targets = sorted(
        str(p)
        for p in REPO_ROOT.rglob("*.md")
        if not any(
            part in {".venv", ".tools", "output", "local_content", ".git", ".pytest_cache"}
            for part in p.relative_to(REPO_ROOT).parts
        )
    )

    lint_targets = ["src", "tests", "scripts"]

    results: dict[str, bool | None] = {
        # Lint/format first: they're the fastest checks and the most likely
        # to fail on a fresh edit, so failing here saves waiting on semgrep.
        "ruff (lint)": run("ruff check", ["ruff", "check", *lint_targets]),
        "ruff (format)": run("ruff format --check", ["ruff", "format", "--check", *lint_targets]),
        "pytest (test suite)": run("pytest", ["pytest", "-q"]),
        "bandit (static security analysis)": run(
            "bandit", ["bandit", "-c", "pyproject.toml", "-r", "src"]
        ),
        "semgrep (broader SAST)": check_semgrep(),
        "pip-audit (dependency CVEs)": run("pip-audit", ["pip-audit"]),
        "pip-audit (semgrep's lock)": run(
            "pip-audit -r requirements/semgrep/semgrep.txt",
            [
                "pip-audit",
                "--disable-pip",
                "--require-hashes",
                "-r",
                "requirements/semgrep/semgrep.txt",
            ],
        ),
        "mdformat (markdown quality)": run(
            "mdformat --check", ["mdformat", "--check", *md_targets]
        ),
        "gitleaks (secrets scan)": check_gitleaks(),
    }

    return summarise(results, allow_skip)


def summarise(results: dict[str, bool | None], allow_skip: set[str]) -> int:
    """Print the summary and return the exit code.

    Separate from `main` so the exit rule can be tested without installing
    or uninstalling tools. The rule it encodes: a check that did not run is
    not a check that passed.
    """
    # A check that declined to run but has no --allow-skip name would
    # fall out of the accounting below and be reported as a pass. Stop
    # instead: the failure mode this whole change exists to remove is
    # exactly "absent, and therefore counted as fine".
    undeclared = [
        label for label, passed in results.items() if passed is None and label not in SKIP_FLAGS
    ]
    if undeclared:
        print(
            f"\nBUG in check.py: check(s) skipped with no SKIP_FLAGS entry: {undeclared}",
            file=sys.stderr,
        )
        return 2

    skipped = [label for label, passed in results.items() if passed is None]
    unacknowledged = [label for label in skipped if SKIP_FLAGS[label] not in allow_skip]

    # What did NOT run comes first, before the wall of PASS. A reader
    # scanning a summary is looking for the word FAIL, and a SKIP sitting
    # seventh in a list of nine reads as noise next to eight passes.
    print(f"\n{'=' * 60}\nSummary\n{'=' * 60}")
    if skipped:
        print(f"  {len(skipped)} of {len(results)} checks DID NOT RUN:")
        for label in skipped:
            note = "" if SKIP_FLAGS[label] in allow_skip else "  <- not acknowledged"
            print(f"      {label}{note}")
        print()

    for label, passed in results.items():
        status = "SKIP" if passed is None else ("PASS" if passed else "FAIL")
        print(f"  {status}  {label}")

    failed = [label for label, passed in results.items() if passed is False]
    print(f"\n  {len(results) - len(skipped)} ran, {len(failed)} failed, {len(skipped)} skipped")

    if unacknowledged:
        # The whole point of this script is to answer "is this safe to
        # push". A tool that is absent has produced no evidence, and
        # reporting its absence as success is the one answer that cannot
        # be recovered from downstream: the reader has already stopped
        # looking. Acknowledging a skip is cheap and leaves a record of
        # who decided the gap was acceptable.
        flags = " ".join(f"--allow-skip {SKIP_FLAGS[label]}" for label in unacknowledged)
        print(
            f"\n  FAILING because {len(unacknowledged)} check(s) did not run.\n"
            f"  Install the missing tool (each SKIP above says how), or accept\n"
            f"  the gap explicitly:\n\n      python scripts/check.py {flags}\n"
        )
        return 1

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
