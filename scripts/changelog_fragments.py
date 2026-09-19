#!/usr/bin/env python3
"""Assemble `changelog.d/` fragments into a release section of CHANGELOG.md.

WHY THIS EXISTS. One `## Unreleased` section means every pair of branches
shipping anything user-visible edits the same place in the same file, so
every pair conflicts. In a single sitting on 2026-09-18 that produced:

  - four hand-resolved conflicts in `Unreleased`
  - one resolution that silently converted 1,768 lines to CRLF, found by
    diffing a normalised copy rather than by running the formatter, which
    would have rewritten every line and hidden the one real change
  - one resolution that left an entry as a `###` heading, so five unrelated
    entries nested under "The HIPAA catalog verifies" — no conflict, no
    failing check, every merge individually correct, and only visible in the
    assembled text after the fifth merge
  - two user-visible merges that shipped with no entry at all

Every one of those is a property of *where the text lives*, not of anyone's
care. `scripts/changelog_guard.py` (#126) makes the last of them fail CI.
This removes the cause of the other three: a fragment is a new file, and new
files do not conflict.

WHAT THIS DOES NOT DO, deliberately. It does not order the entries, group
them into categories, or invent headings. This changelog's voice is bold-lead
paragraphs in a deliberate narrative order — breaking changes first, the
reason before the remedy — and a tool that imposed `### Added` / `### Fixed`
would flatten that into something nobody here would have written. Assembly
emits fragments in filename order and the person cutting the release arranges
them, **once, in one file, with no conflict to resolve**. The value is
removing the conflict, not automating the judgement.

Usage:

    python scripts/changelog_fragments.py --check          # CI: are they well-formed
    python scripts/changelog_fragments.py --version 1.5.0  # cut the section
    python scripts/changelog_fragments.py --version 1.5.0 --dry-run

Writing one: a file in `changelog.d/` named after your branch, holding the
prose you would otherwise have put under `## Unreleased`. See
`changelog.d/README.md`.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
FRAGMENT_DIR = REPO_ROOT / "changelog.d"
CHANGELOG = REPO_ROOT / "CHANGELOG.md"

#: `README.md` documents the convention and is never an entry.
NOT_A_FRAGMENT = {"README.md"}

#: Where a new section is inserted: immediately before the newest existing
#: release heading, so the file stays newest-first without needing to know
#: what the previous version was.
RELEASE_HEADING = re.compile(r"^## \d+\.\d+\.\d+", re.MULTILINE)


def fragments(directory: Path | None = None) -> list[Path]:
    """Fragment files in filename order, excluding the README."""
    directory = directory or FRAGMENT_DIR
    if not directory.is_dir():
        return []
    return sorted(p for p in directory.glob("*.md") if p.name not in NOT_A_FRAGMENT)


def check(paths: list[Path]) -> list[str]:
    """Complaints about fragments that would assemble into something wrong.

    Deliberately few, and each is a thing that produced a real defect:
    an empty fragment means someone opened the file and did not write the
    entry; a `## ` heading would create a second release section inside the
    one being cut; a CR is the 1,768-line conversion in miniature.
    """
    problems = []
    for path in paths:
        raw = path.read_bytes()
        text = raw.decode("utf-8", errors="replace")
        if not text.strip():
            problems.append(f"{path.name}: empty — write the entry or delete the file")
        if b"\r" in raw:
            problems.append(f"{path.name}: contains CR; write it with LF endings")
        for line in text.splitlines():
            if line.startswith("## "):
                problems.append(
                    f"{path.name}: starts a `## ` section. A fragment is the prose that "
                    "goes *under* a release heading; the heading is added at assembly."
                )
                break
    return problems


def assemble(paths: list[Path], version: str) -> str:
    """The new release section, heading included, ending with one blank line."""
    bodies = [p.read_text(encoding="utf-8").strip() for p in paths]
    return f"## {version}\n\n" + "\n\n".join(bodies) + "\n\n"


def insert(changelog_text: str, section: str) -> str:
    """`section` placed above the newest existing release heading."""
    match = RELEASE_HEADING.search(changelog_text)
    if not match:
        raise SystemExit("changelog_fragments: no `## <x.y.z>` heading found in CHANGELOG.md")
    return changelog_text[: match.start()] + section + changelog_text[match.start() :]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="validate fragments and stop")
    parser.add_argument("--version", help="version to cut, e.g. 1.5.0")
    parser.add_argument("--dry-run", action="store_true", help="print, change nothing")
    args = parser.parse_args(argv or [])

    found = fragments()
    problems = check(found)

    # The size of what was examined, always — a check that found nothing and
    # a check that ran over nothing are the same output otherwise.
    print(f"changelog fragments: {len(found)} in {FRAGMENT_DIR.name}/")
    for path in found:
        print(f"    {path.name}")
    for problem in problems:
        print(f"  PROBLEM  {problem}")
    if problems:
        return 1

    if args.check:
        return 0
    if not args.version:
        parser.error("--version is required unless --check")
    if not found:
        print("Nothing to assemble: no fragments. Is this release intentionally silent?")
        return 1

    section = assemble(found, args.version)
    if args.dry_run:
        print(f"\n--- would insert above the newest release heading ---\n{section}")
        return 0

    CHANGELOG.write_text(
        insert(CHANGELOG.read_text(encoding="utf-8"), section), encoding="utf-8", newline="\n"
    )
    for path in found:
        path.unlink()
    print(
        f"\nWrote ## {args.version} from {len(found)} fragment(s) and removed them.\n"
        "Now READ the assembled section top to bottom and arrange it: this tool\n"
        "emits filename order and has no opinion about what belongs first. The\n"
        "entries that change someone's exit codes belong at the top."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
