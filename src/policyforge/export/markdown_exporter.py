"""Writes generated documents to output/ as plain markdown.

This is the primary export path (see README's "Output format priority") —
Confluence export (confluence_exporter.py) converts this same output rather
than generating separately. `check_markdown_quality` is the enforcement
mechanism: call it before treating generated output as final.

output/ is gitignored (see .gitignore) since generated policies contain
org-specific context that shouldn't land in this public repo.
"""

from __future__ import annotations

from pathlib import Path

import mdformat


def write_markdown(content: str, *, output_dir: Path, filename: str) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / filename
    path.write_text(content, encoding="utf-8")
    return path


def check_markdown_quality(path: Path) -> bool:
    """Checks a generated file against mdformat's formatting rules — the
    same tool enforced repo-wide in pre-commit/CI (see
    .pre-commit-config.yaml). Uses mdformat's Python API directly (not a
    subprocess call) so this can run as part of the generation pipeline
    without shelling out. A generation pipeline should call this before
    treating output as final; a mismatch means the markdown isn't
    well-formed CommonMark and shouldn't be shipped or handed to the
    Confluence exporter.
    """
    original = path.read_text(encoding="utf-8")
    formatted = mdformat.text(original, extensions={"gfm"})
    return original == formatted
