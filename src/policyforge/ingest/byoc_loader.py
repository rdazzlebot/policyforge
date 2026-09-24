"""Bring-your-own-content loader for licensed frameworks (HITRUST CSF,
GovRAMP, or anything else you don't have redistribution rights to).

This module only ever reads from `local_content/<framework>/`, which is
gitignored. It never writes into `data/frameworks/` (the bundled/public
directory) and never makes a network call. Treat that as an invariant --
if you extend this, keep the "reads BYOC in, never writes BYOC to a
bundled/public path" boundary. `tests/test_byoc_boundary.py` walks this
module's AST to enforce it, so the invariant fails a test run rather than
somebody's licence.

HITRUST and GovRAMP are both implemented, each as a pair of modules on
the same split: one holding what the framework *is*, one holding how to
find it in the file it arrives in.

`ingest/hitrust.py` holds what HITRUST is
-- the Category / Objective / Control Reference / Requirement hierarchy,
the split between maturity levels and regulatory overlays, and the
authoritative-source crosswalk -- and `ingest/hitrust_export.py` knows how
to find those things in a MyCSF CSV, workbook, HTML or MHTML export. Column
headers in a MyCSF CSV are SQL Server Reporting Services textbox names
(`Textbox52`, `Textbox105`) and identify nothing, so fields are recognised
by their caption columns and by the shape of their values instead.

`ingest/govramp.py` holds what GovRAMP is -- a profile over 800-53 rather
than a catalog, carrying the parameter values and added requirements the
base catalog leaves open, across three verification tiers that are not
impact levels -- and `ingest/govramp_export.py` knows how to find the one
controls sheet inside a fourteen-sheet SSP template whose header spans two
rows.

That covers the exports people have. It cannot cover the export nobody has
seen yet, which is why `policyforge generate-parser --framework
hitrust|govramp --sample <path>` still exists: when detection cannot find
the fields, it says which ones are missing, and the codegen path drafts a
loader for that specific file from a sample (see
`ingest/parser_codegen.py`).
"""

from __future__ import annotations

from pathlib import Path

from .govramp_export import load as _load_govramp
from .hitrust_export import load as _load_hitrust
from .schema import Control


def load_hitrust_export(
    export_path: Path, *, version: str = "", losses: list[str] | None = None
) -> list[Control]:
    """Parse a HITRUST CSF export into `Control` objects, in memory.

    Accepts the renderings MyCSF produces: `.csv`, `.tsv`, `.xlsx`,
    `.xlsm`, `.html`, `.htm`, `.mhtml`, `.mht`. Prefer the CSV where you
    have a choice -- the rendered report carries markedly fewer
    authoritative-source mappings than the data export of the same report.

    `losses`, when given, collects warnings for text a rendered report could
    not place (#266); the caller decides how to show them.

    `version` stamps the catalog (e.g. "v11.7"). Left empty, it is taken
    from the filename if that names one, because a MyCSF export states its
    CSF release nowhere inside the file.

    Returns controls and nothing else. Persisting them is the caller's
    decision, and a licensed catalog written into `data/frameworks/` would
    be committed and redistributed -- so this function has no path
    argument, no output directory, and no serialization step.
    """
    return _load_hitrust(Path(export_path), version=version, losses=losses)


def load_govramp_export(
    export_path: Path, *, version: str = "", impact_level: str = ""
) -> list[Control]:
    """Parse a GovRAMP controls matrix into `Control` objects, in memory.

    Takes the published workbook (`.xlsx`/`.xlsm`) as GovRAMP ships it --
    the SSP template, not an extract of it. The controls sheet is found
    among the template's other thirteen by its header captions, so the Low,
    Moderate and High workbooks all read without being told which they are.

    `version` and `impact_level` override what the file says about itself,
    which is worth doing on a workbook somebody has already been working
    in: the cover sheet that states both is usually the first thing edited.

    GovRAMP's Terms & Conditions claim ownership of the documents published
    on their site and no redistribution grant was found, so this is BYOC on
    the same footing as HITRUST: you supply the workbook, it is parsed
    locally, and -- as with every function here -- nothing is written.
    Returning controls and taking no output path is the point, not an
    oversight.
    """
    return _load_govramp(Path(export_path), version=version, impact_level=impact_level)
