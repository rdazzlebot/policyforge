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

Optional: install the gitleaks binary to get the secrets scan locally too
(Windows: `winget install gitleaks.gitleaks`; otherwise download from
https://github.com/gitleaks/gitleaks/releases). Without it, that one check
is skipped with a note, not silently ignored.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


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


def main() -> int:
    # Every markdown file the pre-commit mdformat hook would touch, so this
    # script and that hook can't disagree about what "formatted" means. Only
    # output/ is excluded — it holds generated drafts, which are checked by
    # `check_markdown_quality` at generation time instead.
    md_targets = sorted(
        str(p)
        for p in REPO_ROOT.rglob("*.md")
        if not any(
            part in {".venv", "output", "local_content", ".git", ".pytest_cache"}
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
        "semgrep (broader SAST)": run(
            "semgrep",
            [
                "semgrep",
                "scan",
                "--config=p/python",
                "--config=p/security-audit",
                "--config=p/owasp-top-ten",
                "--error",
                ".",
            ],
        ),
        "pip-audit (dependency CVEs)": run("pip-audit", ["pip-audit"]),
        "mdformat (markdown quality)": run(
            "mdformat --check", ["mdformat", "--check", *md_targets]
        ),
        "gitleaks (secrets scan)": check_gitleaks(),
    }

    print(f"\n{'=' * 60}\nSummary\n{'=' * 60}")
    all_passed = True
    for label, passed in results.items():
        status = "SKIP" if passed is None else ("PASS" if passed else "FAIL")
        print(f"  {status}  {label}")
        if passed is False:
            all_passed = False

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
