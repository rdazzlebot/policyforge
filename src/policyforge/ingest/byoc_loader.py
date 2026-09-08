"""Bring-your-own-content loader for licensed frameworks (HITRUST CSF,
GovRAMP, or anything else you don't have redistribution rights to).

This module only ever reads from `local_content/<framework>/`, which is
gitignored. It never writes into `data/frameworks/` (the bundled/public
directory) and never makes a network call. Treat that as an invariant --
if you extend this, keep the "reads BYOC in, never writes BYOC to a
bundled/public path" boundary. `tests/test_byoc_boundary.py` walks this
module's AST to enforce it, so the invariant fails a test run rather than
somebody's licence.

HITRUST is implemented. `ingest/hitrust.py` holds what the framework *is*
-- the Category / Objective / Control Reference / Requirement hierarchy,
the split between maturity levels and regulatory overlays, and the
authoritative-source crosswalk -- and `ingest/hitrust_export.py` knows how
to find those things in a MyCSF CSV, workbook, HTML or MHTML export. Column
headers in a MyCSF CSV are SQL Server Reporting Services textbox names
(`Textbox52`, `Textbox105`) and identify nothing, so fields are recognised
by their caption columns and by the shape of their values instead.

That covers the exports people have. It cannot cover the export nobody has
seen yet, which is why `policyforge generate-parser --framework hitrust
--sample <path>` still exists: when detection cannot find the fields, it
says which ones are missing, and the codegen path drafts a loader for that
specific file from a sample (see `ingest/parser_codegen.py`).

GovRAMP remains a stub pending a sample export.
"""

from __future__ import annotations

from pathlib import Path

from .hitrust_export import load as _load_hitrust
from .schema import Control


def load_hitrust_export(export_path: Path, *, version: str = "") -> list[Control]:
    """Parse a HITRUST CSF export into `Control` objects, in memory.

    Accepts the renderings MyCSF produces: `.csv`, `.tsv`, `.xlsx`,
    `.xlsm`, `.html`, `.htm`, `.mhtml`, `.mht`. Prefer the CSV where you
    have a choice -- the rendered report carries markedly fewer
    authoritative-source mappings than the data export of the same report.

    `version` stamps the catalog (e.g. "v11.7"). Left empty, it is taken
    from the filename if that names one, because a MyCSF export states its
    CSF release nowhere inside the file.

    Returns controls and nothing else. Persisting them is the caller's
    decision, and a licensed catalog written into `data/frameworks/` would
    be committed and redistributed -- so this function has no path
    argument, no output directory, and no serialization step.
    """
    return _load_hitrust(Path(export_path), version=version)


def load_govramp_export(export_path: Path) -> list[Control]:
    raise NotImplementedError(
        "Point this at your GovRAMP baseline export and implement parsing. "
        "Note: as of writing, GovRAMP's Terms & Conditions claim ownership "
        "of their published documents with no redistribution grant found -- "
        "treat this as BYOC (like HITRUST) unless/until GovRAMP grants "
        "permission. See README's licensing table. If your export is a "
        "table, `ingest/hitrust_export.py`'s column detection is a working "
        "model to copy."
    )
