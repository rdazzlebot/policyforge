"""Reading the files a HITRUST CSF export actually arrives in.

`hitrust.py` describes the framework. This module knows about MyCSF's
report renderings, which come in two families:

* **A table** -- CSV, TSV or a workbook. One row per (control reference x
  level), with the tier columns repeated down every row. Column *headers*
  are SSRS textbox names, so they identify nothing.
* **A rendered report** -- HTML, or MHTML, which is one base64 HTML part in
  a MIME envelope. Laid out as label/value pairs down the page, with the
  tier printed once as a heading and each level's block beneath it.

The rendered form is in some ways the easier of the two, because SSRS
prints the human label beside every value: "Control Reference:", "Level
FedRAMP Implementation:". The table form has those same labels -- it just
puts them in *caption columns* next to the values they describe, which is
the trick `detect_fields` leans on. In a v11.7 CSV, `Textbox104` holds
nothing but the string "Level 1 Organizational Factors:" and the column
immediately after it holds the factors. So the export documents itself, one
column to the left.

Where captions run out, columns are identified by what their values look
like: a column of `01.a Access Control Policy` is the reference column no
matter what SSRS called it.

**Prefer the CSV.** Both renderings of the same v11.7 report are readable,
and they do not carry the same amount. The CSV holds 1,219 requirement
statements and a mapping list on nearly every one; the MHTML of that same
report holds 1,194 statements and only 373 mapping blocks, because the
rendered layout suppresses repeats the data export keeps. Read the MHTML
when it is what somebody has -- it is the better-labelled file and it
recovers level names the CSV truncates -- but a crosswalk built from it
will be missing most of its edges, and `hitrust.summarize` will say so.

Nothing here is guaranteed to work on an export shape nobody has seen. When
detection cannot find the fields a HITRUST record needs, `load` says which
ones are missing and points at `policyforge generate-parser`, which drafts
a loader for that specific file. Failing with a list of missing fields is
the point: a heuristic that quietly returned half a catalog would be worse
than one that stops.
"""

from __future__ import annotations

import csv
import email
import re
from collections.abc import Iterable
from html.parser import HTMLParser
from pathlib import Path

from . import hitrust
from .hitrust import Record

#: Fields without which a record is not a HITRUST requirement statement.
#: Everything else enriches; these four are the identity.
REQUIRED_FIELDS = ("reference", "level", "statement")

#: Fields a table's caption columns or headers may name.
TABLE_FIELDS = tuple(hitrust.FIELD_ALIASES)

#: Rows sampled when identifying a column by its contents. The whole point
#: of sampling is that a 10MB export should not be scanned twice.
SAMPLE_ROWS = 400

#: How much of a sampled column must match a pattern before the column is
#: called by it. Below 1.0 because a report footer or a blank spacer row
#: can put one stray value in an otherwise uniform column.
MATCH_RATIO = 0.8

CSV_SUFFIXES = {".csv", ".tsv", ".txt"}
WORKBOOK_SUFFIXES = {".xlsx", ".xlsm"}
HTML_SUFFIXES = {".html", ".htm"}
MHTML_SUFFIXES = {".mhtml", ".mht"}


class ExportFormatError(RuntimeError):
    """Raised when an export cannot be read as HITRUST at all."""


# --------------------------------------------------------------------------
# Column detection
# --------------------------------------------------------------------------


def _non_empty(values: Iterable[str]) -> list[str]:
    return [" ".join(str(v).split()) for v in values if v and str(v).strip()]


def _ratio(values: list[str], predicate) -> float:
    if not values:
        return 0.0
    return sum(1 for v in values if predicate(v)) / len(values)


def detect_fields(header: list[str], rows: list[list[str]]) -> dict[str, int]:
    """Map canonical HITRUST field names onto column indexes.

    Three passes, most trustworthy first:

    1. **Headers.** A column called `Control_Specification` says what it is.
    2. **Caption columns.** A column whose every value is a field label
       describes the column to its right. This is what rescues the
       `Textbox105`-style columns that carry the factors and the mappings.
    3. **Contents.** A column of `01.a ...` values is the reference column;
       a column of `Level ...` values is the level column.

    A field already claimed by an earlier pass is never overwritten, so a
    real header always beats a guess about content.
    """
    sample = rows[:SAMPLE_ROWS]
    assigned: dict[str, int] = {}

    def claim(field: str, index: int) -> None:
        if field not in assigned and 0 <= index < len(header):
            assigned[field] = index

    for index, name in enumerate(header):
        field = hitrust.field_for_label(name)
        if field:
            claim(field, index)

    for index in range(len(header) - 1):
        values = _non_empty(row[index] for row in sample if index < len(row))[:60]
        if not values:
            continue
        labelled = [hitrust.field_for_label(v) for v in values]
        named = {f for f in labelled if f}
        # A caption column says the same thing in every row. Two different
        # field labels in one column means it is data, not a caption.
        if len(named) == 1 and _ratio(labelled, bool) >= MATCH_RATIO:
            claim(named.pop(), index + 1)

    patterns = (
        ("category", hitrust.CATEGORY_RE.match),
        ("objective", hitrust.OBJECTIVE_RE.match),
        ("reference", hitrust.REFERENCE_RE.match),
        ("level", hitrust.LEVEL_RE.match),
    )
    taken = set(assigned.values())
    for index in range(len(header)):
        if index in taken:
            continue
        values = _non_empty(row[index] for row in sample if index < len(row))
        if not values:
            continue
        for field, matcher in patterns:
            if field not in assigned and _ratio(values, matcher) >= MATCH_RATIO:
                claim(field, index)
                taken.add(index)
                break

    return assigned


def missing_fields(assigned: dict[str, int]) -> list[str]:
    return [f for f in REQUIRED_FIELDS if f not in assigned]


# --------------------------------------------------------------------------
# Tables
# --------------------------------------------------------------------------


def records_from_table(header: list[str], rows: list[list[str]]) -> list[Record]:
    """Turn a detected table into records, one per row.

    Deduplication is left to `hitrust.build_controls`: a reader's job is to
    report what the file says, and 2,818 rows is what the file says.
    """
    assigned = detect_fields(header, rows)
    absent = missing_fields(assigned)
    if absent:
        raise ExportFormatError(
            "could not identify these HITRUST fields in the export: "
            + ", ".join(absent)
            + ". Columns seen: "
            + ", ".join(str(h) for h in header[:24])
        )

    records = []
    for row in rows:
        values = {}
        for field, index in assigned.items():
            values[field] = str(row[index]) if index < len(row) and row[index] else ""
        values.pop("topics", None)
        records.append(Record(**values))
    return records


def read_csv(path: Path) -> tuple[list[str], list[list[str]]]:
    """Read a CSV or TSV export.

    `utf-8-sig` because MyCSF's CSV carries a BOM, and cells hold CRLF line
    breaks inside quotes, which `csv` handles only when the file is opened
    with `newline=""`. The field-size limit is raised because a single
    mapping cell in a full library export runs past 29,000 characters --
    well beyond `csv`'s 128KB default only in aggregate, but the limit is
    cheap insurance against the export that does.
    """
    csv.field_size_limit(2**31 - 1)
    delimiter = "\t" if path.suffix.lower() == ".tsv" else ","
    with path.open(newline="", encoding="utf-8-sig", errors="replace") as handle:
        rows = [list(row) for row in csv.reader(handle, delimiter=delimiter)]
    if not rows:
        raise ExportFormatError(f"{path.name} has no rows.")
    return rows[0], rows[1:]


def read_workbook(path: Path) -> tuple[list[str], list[list[str]]]:
    """Read the first sheet of an .xlsx/.xlsm export."""
    try:
        from openpyxl import load_workbook
    except ImportError as exc:  # pragma: no cover - depends on install extras
        raise ExportFormatError(
            "reading an .xlsx export needs openpyxl (pip install openpyxl)."
        ) from exc

    book = load_workbook(path, read_only=True, data_only=True)
    try:
        sheet = book.active
        rows = [
            ["" if cell is None else str(cell) for cell in row]
            for row in sheet.iter_rows(values_only=True)
        ]
    finally:
        book.close()
    if not rows:
        raise ExportFormatError(f"{path.name} has no rows.")
    return rows[0], rows[1:]


# --------------------------------------------------------------------------
# Rendered reports
# --------------------------------------------------------------------------


class _TableTextParser(HTMLParser):
    """Collect table rows as lists of cell text.

    `<br>` becomes a newline and block ends become boundaries, because a
    factor list and a mapping list are both rendered as one cell of
    `<br/>`-separated lines and their line structure is the data.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[list[str]] = []
        self._row: list[str] = []
        self._cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag == "tr":
            self._row = []
        elif tag in ("td", "th"):
            self._cell = []
        elif tag == "br" and self._cell is not None:
            self._cell.append("\n")

    def handle_startendtag(self, tag: str, attrs) -> None:
        if tag == "br" and self._cell is not None:
            self._cell.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in ("td", "th") and self._cell is not None:
            self._row.append("".join(self._cell))
            self._cell = None
        elif tag in ("div", "p") and self._cell is not None:
            self._cell.append("\n")
        elif tag == "tr":
            if any(cell.strip() for cell in self._row):
                self.rows.append(self._row)
            self._row = []

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)


def _clean(text: str) -> str:
    """Normalize a rendered cell: NBSP out, blank lines out, indent out."""
    lines = [line.replace("\xa0", " ").strip() for line in (text or "").split("\n")]
    return "\n".join(line for line in lines if line)


def read_html_rows(markup: str) -> list[list[str]]:
    parser = _TableTextParser()
    parser.feed(markup)
    parser.close()
    return [[_clean(cell) for cell in row] for row in parser.rows]


def read_mhtml(path: Path) -> str:
    """Pull the HTML part out of an MHTML archive.

    MyCSF's MHTML is a `multipart/related` envelope with a single base64
    `text/html` part -- SSRS writes it as the "web archive" render option.
    Handled with `email` rather than by regex because the base64 body must
    be decoded before any of it means anything.
    """
    message = email.message_from_bytes(path.read_bytes())
    for part in message.walk():
        if part.get_content_type() == "text/html":
            payload = part.get_payload(decode=True)
            if payload:
                charset = part.get_content_charset() or "utf-8"
                return payload.decode(charset, errors="replace")
    # A .mht saved by some browsers is a single quoted-printable part with
    # no multipart wrapper at all.
    raw = path.read_bytes()
    if b"<html" in raw.lower():
        return raw.decode("utf-8", errors="replace")
    raise ExportFormatError(f"{path.name} contains no HTML part.")


#: A rendered report's label column repeats the level for every field it
#: scopes, so a record is keyed by (reference, level) as the page is read.
_LABEL_VALUE_WIDTH = 2


def records_from_pairs(rows: list[list[str]]) -> list[Record]:
    """Read a rendered report's label/value rows into records.

    The page is a stream: tier headings set the context that following
    rows inherit, and each level's block fills in one record. A new
    "Control Reference:" starts a new control; a level-scoped label
    ("Level 2 Implementation:") starts or extends that control's record for
    that level.
    """
    context = Record()
    records: list[Record] = []
    current: dict[str, Record] = {}

    def record_for(level: str) -> Record:
        if level not in current:
            fresh = Record(
                category=context.category,
                objective=context.objective,
                objective_statement=context.objective_statement,
                reference=context.reference,
                specification=context.specification,
                factor_type=context.factor_type,
                level=level,
            )
            current[level] = fresh
            records.append(fresh)
        return current[level]

    for row in rows:
        cells = [cell for cell in row if cell.strip()]
        if len(cells) < _LABEL_VALUE_WIDTH:
            continue
        label, value = cells[-2], cells[-1]
        field = hitrust.field_for_label(label)
        level = hitrust.level_from_label(label)

        if field in ("category", "objective", "objective_statement"):
            setattr(context, field, value)
            current.clear()
            continue
        if field == "reference":
            context.reference = value
            context.specification = ""
            context.factor_type = ""
            current.clear()
            continue
        if field in ("specification", "factor_type"):
            setattr(context, field, value)
            continue
        if field in (
            "statement",
            "organizational_factors",
            "system_factors",
            "regulatory_factors",
            "mapping",
        ):
            if level and context.reference:
                _absorb(record_for(level), field, value)
            continue

    return records


def _absorb(record: Record, field: str, value: str) -> None:
    """Fold a value into a record that may already hold part of it.

    SSRS breaks a long cell across a page boundary and re-prints its label
    on the next page, so one requirement's mapping list can arrive as two
    rows. Overwriting would keep only the tail. List-shaped fields are
    therefore concatenated, while a statement -- which is one paragraph and
    never split in practice -- keeps whichever copy is longer.
    """
    existing = getattr(record, field)
    if not existing:
        setattr(record, field, value)
        return
    if field == "statement":
        if len(value) > len(existing):
            setattr(record, field, value)
        return
    if value not in existing:
        setattr(record, field, existing + "\n" + value)


def records_from_markup(markup: str) -> list[Record]:
    """Read a rendered report, whichever way SSRS laid it out.

    A report rendered as a grid is a table with a header row; a report
    rendered as a form is label/value pairs. Both are tables in the markup,
    so the shape is decided by trying to detect columns and falling back to
    the label/value reader when that finds nothing.
    """
    rows = read_html_rows(markup)
    if not rows:
        raise ExportFormatError("no tables found in the rendered report.")

    widest = max(len(row) for row in rows)
    if widest > 4:
        candidates = [row for row in rows if len(row) == widest]
        header, body = candidates[0], candidates[1:]
        if not missing_fields(detect_fields(header, body)):
            return records_from_table(header, body)

    records = records_from_pairs(rows)
    if not records:
        raise ExportFormatError(
            "the rendered report had no recognisable HITRUST labels "
            '("Control Reference:", "Level 1 Implementation:").'
        )
    return records


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------

#: `CSFLibraryReport_v11.7.csv` -> `v11.7`. Best effort: a version stamped
#: in the filename is the only place a MyCSF export states one.
#:
#: An explicit separator class rather than `\b`, because the separator that
#: actually appears is an underscore -- which is a word character, so `\b`
#: never fires between `Report` and `v11.7` and the version is missed on
#: exactly the filename people use.
_VERSION_RE = re.compile(r"(?:^|[^0-9A-Za-z])v?(\d{1,2}\.\d{1,2}(?:\.\d{1,2})?)(?![0-9.])")


def version_from_name(path: Path) -> str:
    match = _VERSION_RE.search(path.stem)
    return f"v{match.group(1)}" if match else ""


def read_records(path: Path) -> list[Record]:
    """Read any supported HITRUST export into records."""
    suffix = path.suffix.lower()
    if suffix in CSV_SUFFIXES:
        header, rows = read_csv(path)
        return records_from_table(header, rows)
    if suffix in WORKBOOK_SUFFIXES:
        header, rows = read_workbook(path)
        return records_from_table(header, rows)
    if suffix in MHTML_SUFFIXES:
        return records_from_markup(read_mhtml(path))
    if suffix in HTML_SUFFIXES:
        return records_from_markup(path.read_text(encoding="utf-8", errors="replace"))
    raise ExportFormatError(
        f"no reader for {suffix or 'a file with no extension'}. Supported: "
        + ", ".join(sorted(CSV_SUFFIXES | WORKBOOK_SUFFIXES | HTML_SUFFIXES | MHTML_SUFFIXES))
    )


def load(path: Path, *, version: str = "") -> list:
    """Read a HITRUST CSF export into `Control` objects.

    The whole BYOC path in one call: read the file, name its columns,
    deduplicate the report's repeated rows, learn the authoritative-source
    vocabulary from the mappings, and assemble one Control per control
    reference.
    """
    path = Path(path)
    records = read_records(path)
    return hitrust.build_controls(
        records,
        version=version or version_from_name(path),
        source_path=str(path),
    )


__all__ = [
    "ExportFormatError",
    "detect_fields",
    "load",
    "read_records",
    "records_from_markup",
    "records_from_pairs",
    "records_from_table",
    "version_from_name",
]
