#!/usr/bin/env python3
"""Run the full quality-check suite locally, in one command.

Runs the same checks enforced in .pre-commit-config.yaml and
.github/workflows/ci.yml: pytest, bandit (static security analysis),
semgrep (broader SAST — catches patterns bandit's Python-specific ruleset
doesn't, e.g. GitHub Actions supply-chain hygiene), pip-audit (dependency
CVEs), mdformat (markdown quality), and gitleaks (secrets scan, if
installed). Each check is invoked directly rather than through
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
    md_targets = [str(REPO_ROOT / "README.md")]
    md_targets += sorted(
        str(p) for p in (REPO_ROOT / "data" / "frameworks").glob("*/README.md")
    )

    results: dict[str, bool | None] = {
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
