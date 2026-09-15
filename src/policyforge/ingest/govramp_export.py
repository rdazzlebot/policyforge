"""Reading the workbook a GovRAMP controls matrix arrives in.

`govramp.py` describes the framework. This module knows about the file.

A GovRAMP matrix is not a data export the way a MyCSF report is. It is a
**working SSP template**: fourteen sheets, of which one holds the controls
and the rest are a cover page, instructions, dashboards, an inventory
workbook and several blank grids for a service provider to fill in. So the
first job is finding the right sheet, and the second is reading a header
that was laid out for a human.

Three things about that layout drive the design here:

* **The sheet name is not dependable.** It is `12_Mod Controls` in the
  Moderate workbook, and the number is a position in a template that
  GovRAMP renumbers between revisions. The sheet is found by its *header
  captions* instead, scoring every sheet and taking the best -- which also
  means the Low and High workbooks, whose sheet is named differently, need
  no special case.
* **The header is two rows.** Row 1 spans group titles across merged cells
  ("Control Information", "GovRAMP Parameters"); row 2 holds the captions
  that actually name columns. Reading row 1 as the header finds almost
  nothing, and openpyxl returns `None` for every cell of a merged span
  except its first -- so the two rows are merged into one caption per
  column before anything is matched.
* **Captions are prose, and they are not stable.** "NIST Control
  Description\\n (From NIST SP 800-53r5 12/10/2020)" carries a date that
  will change. Matching is therefore on a normalized *substring*, longest
  and most specific first, so a caption that grows a parenthetical still
  resolves.

Below the controls there is a totals row (`80`, `319` sitting under the
tier columns with no identifier beside them) and then a blank tail. Neither
is a control, and both are skipped by the same rule: a row with no
identifier is not a row.

Nothing here is guaranteed to work on a workbook nobody has seen. When the
columns a control needs cannot be found, `load` raises and says which ones
were missing, and `policyforge generate-parser --framework govramp` drafts
a loader for that specific file. Failing with a list of missing fields is
the point: a heuristic that quietly returned two thirds of a baseline would
be read as a smaller baseline, and a scope is the one thing here nobody
re-checks by hand.
"""

from __future__ import annotations

import re
from pathlib import Path

from . import govramp
from .govramp import Row

#: Suffixes openpyxl can read. A GovRAMP matrix is published as .xlsx; the
#: macro-enabled variant is accepted because an organization that has been
#: working in the template often has one.
WORKBOOK_SUFFIXES = {".xlsx", ".xlsm"}

#: Rows scanned at the top of a sheet when looking for its header. The
#: controls sheet puts its captions in rows 1-2; the margin is for a
#: workbook that grows a title row above them.
HEADER_SCAN_ROWS = 6

#: Fields without which a row is not a GovRAMP control. The identifier and
#: the statement are the control; the tier columns are the entire reason to
#: read a GovRAMP matrix rather than the 800-53 catalog it quotes.
REQUIRED_COLUMNS = ("control_id", "statement", "tier_core", "tier_ready", "tier_authorized")

#: Canonical column name -> caption substrings that name it, normalized
#: (lowercased, punctuation and whitespace collapsed). Ordered longest and
#: most specific first within each field, and matched in `_CAPTIONS` order
#: across fields, because several captions are prefixes of others: "id"
#: appears inside "sort id", and "control name" inside "nist control
#: description". A shorter caption tested first would claim the wrong
#: column and the loss would be silent.
_CAPTIONS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("tier_core", ("required for core",)),
    ("tier_ready", ("required for ready",)),
    ("tier_authorized", ("required for authorized", "required for authorization")),
    ("statement", ("nist control description", "control description")),
    ("discussion", ("nist discussion", "discussion")),
    ("parameters", ("defined assignment selection parameters", "parameters")),
    ("additional_requirements", ("additional govramp requirements", "additional requirements")),
    ("sort_id", ("sort id",)),
    ("family", ("family",)),
    ("name", ("control name",)),
    ("control_id", ("id",)),
)

_PUNCT_RE = re.compile(r"[^a-z0-9 ]+")

#: `GovRAMP-Controls-Matrix_Mod_Rev5_V1.06` -> `V1.06`. The workbook states
#: its revision ("Rev. 5") on the cover sheet but never its template
#: version, which is what distinguishes two files of the same revision.
_VERSION_RE = re.compile(r"(?:^|[^0-9A-Za-z])[vV](\d{1,2}\.\d{1,2}(?:\.\d{1,3})?)(?![0-9.])")

#: `Mod` in a filename is Moderate. Matched on a separator boundary so that
#: `Mod` does not fire on a word that merely contains it.
_IMPACT_IN_NAME = (
    ("high", govramp.HIGH),
    ("mod", govramp.MODERATE),
    ("moderate", govramp.MODERATE),
    ("low", govramp.LOW),
)


class ExportFormatError(RuntimeError):
    """Raised when a workbook cannot be read as a GovRAMP controls matrix."""


# --------------------------------------------------------------------------
# Captions
# --------------------------------------------------------------------------


def _normalize(text: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace.

    Applied to captions before matching so that "NIST Control
    Description\\n (From NIST SP 800-53r5 12/10/2020)" and "NIST Control
    Description" are the same string as far as detection is concerned.
    """
    return " ".join(_PUNCT_RE.sub(" ", str(text or "").lower()).split())


def merge_header(header_rows: list[list[str]]) -> list[str]:
    """Collapse a multi-row header into one caption per column.

    The group title in row 1 and the caption in row 2 are joined, in that
    order, so a column can be identified by either. Blank cells contribute
    nothing, which is what makes this safe on the merged spans openpyxl
    reports as `None` everywhere but their first cell.
    """
    width = max((len(row) for row in header_rows), default=0)
    merged = []
    for index in range(width):
        parts = [
            str(row[index]).strip()
            for row in header_rows
            if index < len(row) and row[index] and str(row[index]).strip()
        ]
        merged.append(" ".join(parts))
    return merged


def detect_columns(header: list[str]) -> dict[str, int]:
    """Map canonical column names onto column indexes.

    A field already claimed is never reassigned, and a column already taken
    by an earlier field is never claimed twice -- which is what keeps the
    bare caption `ID` from matching `SORT ID` once `sort_id` has taken it.
    """
    normalized = [_normalize(caption) for caption in header]
    assigned: dict[str, int] = {}
    taken: set[int] = set()

    for field, needles in _CAPTIONS:
        for needle in needles:
            match = next(
                (
                    index
                    for index, caption in enumerate(normalized)
                    if caption and index not in taken and needle in caption
                ),
                None,
            )
            if match is not None:
                assigned[field] = match
                taken.add(match)
                break
    return assigned


def missing_columns(assigned: dict[str, int]) -> list[str]:
    return [field for field in REQUIRED_COLUMNS if field not in assigned]


def score_sheet(header: list[str]) -> int:
    """How much of a GovRAMP controls header a sheet's captions look like.

    Used to pick the controls sheet out of the workbook. Counting matched
    columns rather than testing for a known sheet name is what lets the Low
    and High workbooks -- and a template that renumbers its sheets --
    through without a special case.
    """
    return len(detect_columns(header))


# --------------------------------------------------------------------------
# The workbook
# --------------------------------------------------------------------------


def _load_workbook(path: Path):
    try:
        from openpyxl import load_workbook
    except ImportError as exc:  # pragma: no cover - depends on install extras
        raise ExportFormatError(
            "reading a GovRAMP matrix needs openpyxl (pip install openpyxl)."
        ) from exc
    try:
        return load_workbook(path, read_only=True, data_only=True)
    # Deliberately broad: openpyxl raises a zoo of types for a file that is
    # not a workbook (zipfile, KeyError, its own InvalidFileException), and
    # every one of them means the same thing to a caller. Re-raised as this
    # module's own error rather than swallowed.
    except Exception as exc:
        raise ExportFormatError(f"{path.name} could not be opened as a workbook: {exc}") from exc


def _cells(sheet, limit: int | None = None) -> list[list[str]]:
    rows = []
    for index, row in enumerate(sheet.iter_rows(values_only=True)):
        if limit is not None and index >= limit:
            break
        rows.append(["" if cell is None else str(cell) for cell in row])
    return rows


def find_controls_sheet(book) -> tuple[str, list[str], int]:
    """Pick the controls sheet, and say where its data starts.

    Returns `(sheet title, merged header, first data row index)`. The header
    may span one row or two, so both are tried on every sheet and the
    better-scoring split wins -- a one-row read of a two-row header matches
    almost nothing, which makes the comparison decisive rather than close.
    """
    best: tuple[int, str, list[str], int] | None = None

    for sheet in book.worksheets:
        top = _cells(sheet, limit=HEADER_SCAN_ROWS)
        if not top:
            continue
        for start in range(min(len(top), HEADER_SCAN_ROWS - 1)):
            for depth in (2, 1):
                block = top[start : start + depth]
                if not block:
                    continue
                header = merge_header(block)
                score = score_sheet(header)
                if best is None or score > best[0]:
                    best = (score, sheet.title, header, start + depth)

    if best is None:
        raise ExportFormatError("the workbook has no readable sheets.")

    score, title, header, data_start = best
    # Two columns could be coincidence in any grid of prose. The controls
    # sheet matches nine or ten.
    if score < 4:
        raise ExportFormatError(
            "no sheet in this workbook looks like a GovRAMP controls matrix "
            f"(best match: {title!r}, {score} recognised columns). Expected "
            "captions like 'Required for Core', 'NIST Control Description' "
            "and 'Control Name'."
        )
    return title, header, data_start


def read_rows(path: Path) -> tuple[list[Row], dict[str, int]]:
    """Read a workbook's controls sheet into `Row` objects.

    Returns the rows and the detected column map, so a caller can report
    what was found as well as what it produced.
    """
    book = _load_workbook(path)
    try:
        return _rows_from_book(book), _columns_of(book)[1]
    finally:
        book.close()


def _columns_of(book) -> tuple[str, dict[str, int], int]:
    title, header, data_start = find_controls_sheet(book)
    columns = detect_columns(header)
    absent = missing_columns(columns)
    if absent:
        raise ExportFormatError(
            f"sheet {title!r} is missing the column(s): {', '.join(absent)}. "
            f"Captions found: {', '.join(c for c in header if c) or '(none)'}"
        )
    return title, columns, data_start


def _rows_from_book(book) -> list[Row]:
    title, columns, data_start = _columns_of(book)
    cells = _cells(book[title])[data_start:]

    def value(row: list[str], field: str) -> str:
        index = columns.get(field)
        if index is None or index >= len(row):
            return ""
        return row[index].strip()

    rows = []
    for raw in cells:
        row = Row(
            control_id=value(raw, "control_id"),
            sort_id=value(raw, "sort_id"),
            family=value(raw, "family"),
            name=value(raw, "name"),
            statement=value(raw, "statement"),
            discussion=value(raw, "discussion"),
            parameters=value(raw, "parameters"),
            additional_requirements=value(raw, "additional_requirements"),
            tiers={
                govramp.CORE: govramp.is_affirmative(value(raw, "tier_core")),
                govramp.READY: govramp.is_affirmative(value(raw, "tier_ready")),
                govramp.AUTHORIZED: govramp.is_affirmative(value(raw, "tier_authorized")),
            },
        )
        # The totals row under the tier columns and the blank tail both land
        # here with no identifier. Skipped rather than reported: they are
        # part of the template, not a parse failure.
        if row.is_populated:
            rows.append(row)

    if not rows:
        raise ExportFormatError(
            f"sheet {title!r} has the right columns but no control rows under them."
        )
    return rows


# --------------------------------------------------------------------------
# Workbook metadata
# --------------------------------------------------------------------------


def impact_level_from_book(book) -> str:
    """The impact level, from the cover sheet or the instructions.

    The Moderate workbook says "Moderate Baseline" on its cover and "GovRAMP
    Controls Matrix for Moderate Impact System" at the top of its
    instructions. Either will do; only the first few rows of the first few
    sheets are scanned, because this is a hint and not worth a full pass.
    """
    for sheet in book.worksheets[:3]:
        for row in _cells(sheet, limit=12):
            for cell in row:
                text = _normalize(cell)
                for level in govramp.IMPACT_LEVELS:
                    if f"{level.lower()} baseline" in text or f"{level.lower()} impact" in text:
                        return level
    return ""


def impact_level_from_name(path: Path) -> str:
    """`GovRAMP-Controls-Matrix_Mod_Rev5_V1.06.xlsx` -> `"Moderate"`.

    The fallback when the cover sheet has been edited away, which happens
    as soon as somebody starts filling the template in.
    """
    tokens = set(re.split(r"[^A-Za-z0-9]+", path.stem.lower()))
    for token, level in _IMPACT_IN_NAME:
        if token in tokens:
            return level
    return ""


def version_from_name(path: Path) -> str:
    match = _VERSION_RE.search(path.stem)
    return f"V{match.group(1)}" if match else ""


def revision_from_book(book) -> str:
    """`"Rev 5"` from the cover sheet, which is where the workbook states it."""
    for sheet in book.worksheets[:3]:
        for row in _cells(sheet, limit=12):
            for cell in row:
                match = re.search(r"\brev\.?\s*(\d{1,2})\b", str(cell), re.IGNORECASE)
                if match:
                    return f"Rev {match.group(1)}"
    return ""


def describe_version(path: Path, book) -> str:
    """`"Rev 5 (V1.06)"` -- the catalog revision, and the template version.

    Both matter and neither is sufficient: the revision says which 800-53
    the matrix profiles, and the template version distinguishes two
    workbooks of that revision whose parameter values differ.
    """
    revision = revision_from_book(book)
    template = version_from_name(path)
    if revision and template:
        return f"{revision} ({template})"
    return revision or template


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------


def load_with_rows(path: Path, *, version: str = "", impact_level: str = "") -> tuple[list, list]:
    """Read a GovRAMP controls matrix into `(controls, rows)`.

    The whole BYOC path in one call: open the workbook, find the controls
    sheet among the template's other thirteen, name its columns, read the
    rows, and assemble one Control per base control with its enhancements
    folded in.

    The flat rows come back alongside the controls because
    `govramp.summarize` checks the tier columns for GovRAMP's
    Core-inside-Ready-inside-Authorized nesting, and that check needs the
    sheet's own layout rather than the assembled tree. One open for both:
    these workbooks run to several megabytes and most of that is an
    inventory sheet nothing here reads.

    `version` and `impact_level` override what the file says about itself.
    Both are worth overriding on a workbook somebody has been working in,
    where the cover sheet is often the first thing edited.
    """
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix not in WORKBOOK_SUFFIXES:
        raise ExportFormatError(
            f"no reader for {suffix or 'a file with no extension'}. A GovRAMP "
            "controls matrix is a workbook: " + ", ".join(sorted(WORKBOOK_SUFFIXES))
        )

    book = _load_workbook(path)
    try:
        rows = _rows_from_book(book)
        resolved_level = (
            impact_level or impact_level_from_book(book) or impact_level_from_name(path)
        )
        resolved_version = version or describe_version(path, book)
    finally:
        book.close()

    controls = govramp.build_controls(
        rows,
        impact_level=resolved_level,
        version=resolved_version,
        source_path=str(path),
    )
    return controls, rows


def load(path: Path, *, version: str = "", impact_level: str = "") -> list:
    """`load_with_rows`, keeping only the controls."""
    controls, _ = load_with_rows(path, version=version, impact_level=impact_level)
    return controls


__all__ = [
    "ExportFormatError",
    "describe_version",
    "detect_columns",
    "find_controls_sheet",
    "impact_level_from_book",
    "impact_level_from_name",
    "load",
    "load_with_rows",
    "merge_header",
    "missing_columns",
    "read_rows",
    "score_sheet",
    "version_from_name",
]
