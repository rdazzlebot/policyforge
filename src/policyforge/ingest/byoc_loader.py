"""Bring-your-own-content loader for licensed frameworks (HITRUST CSF,
GovRAMP, or anything else you don't have redistribution rights to).

This module only ever reads from `local_content/<framework>/`, which is
gitignored. It never writes into `data/frameworks/` (the bundled/public
directory) and never makes a network call. Treat that as an invariant —
if you extend this, keep the "reads BYOC in, never writes BYOC to a
bundled/public path" boundary.

Exact parsing logic depends on the export format of your license (e.g. a
MyCSF CSV/Excel export for HITRUST). This is a stub: once you have a sample
file in hand, either hand-write `load_hitrust_export` / `load_govramp_export`
against its actual columns, or run
`policyforge generate-parser --framework hitrust --sample <path>` (see
`ingest/parser_codegen.py`) to have your configured LLM draft one from the
sample — that command writes a standalone `<framework>_loader.py`, which you
should review, test, and commit like any other source file before relying
on it in place of the stub below.
"""

from __future__ import annotations

from pathlib import Path

from .schema import Control


def load_hitrust_export(export_path: Path) -> list[Control]:
    raise NotImplementedError(
        "Point this at your MyCSF/HITRUST CSF export and implement parsing "
        "for its actual column layout. Keep the output in-memory / in "
        "local_content/ only — never write parsed HITRUST content into "
        "data/frameworks/."
    )


def load_govramp_export(export_path: Path) -> list[Control]:
    raise NotImplementedError(
        "Point this at your GovRAMP baseline export and implement parsing. "
        "Note: as of writing, GovRAMP's Terms & Conditions claim ownership "
        "of their published documents with no redistribution grant found — "
        "treat this as BYOC (like HITRUST) unless/until GovRAMP grants "
        "permission. See README's licensing table."
    )
