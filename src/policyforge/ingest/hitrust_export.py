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


#: The three outcomes every row of text ends in (#281). `records_from_pairs`
#: records one per non-empty row into `ledger` when given, so a test can
#: assert they PARTITION the input: nothing may leave every outcome.
PLACED, QUIET, REPORTED = "placed", "quiet", "reported"

#: Labels this reader knows and deliberately does not keep. Enumerated, so a
#: quiet row is a decision someone wrote down, not a default.
_KNOWN_UNREAD = frozenset({"topics"})


def records_from_pairs(
    rows: list[list[str]],
    losses: list[str] | None = None,
    ledger: list[tuple[str, list[str]]] | None = None,
) -> list[Record]:
    """Read a rendered report's label/value rows into records.

    The page is a stream: tier headings set the context that following
    rows inherit, and each level's block fills in one record. A new
    "Control Reference:" starts a new control; a level-scoped label
    ("Level 2 Implementation:") starts or extends that control's record for
    that level.

    **Two things this discards, and neither can be ruled out** (#266). Both
    rest on how SSRS lays out a page break, and no real export has been
    seen by this project -- the fixture is our belief about the format:

    - a row carrying text but no label (a cell continued onto the next page
      *without* its label reprinted) is skipped, so its text is lost;
    - a statement that arrives as two different copies keeps the longer
      (`_absorb`), so the shorter is lost -- including in the shape SSRS is
      assumed to produce, with the label reprinted.

    The parse is unchanged; what changed is that neither is silent. Each is
    described into `losses` when given, and `etl-hitrust` prints them as
    warnings, so an export that hits either shape says so on its first run.

    **Every row with text is placed, deliberately quiet, or reported**
    (#277, and 1d on #281). Quiet is an enumerated set -- a bare label with
    no value, a label in `_KNOWN_UNREAD`, and a level heading whose two
    cells are both captions ("Level 1 | Implementation Requirements").
    Anything else nothing placed is REPORTED by default: a row of three or
    more cells whose label is not second-to-last (read as text plus an
    extra cell, taking its level record with it), a label this reader does
    not know, colon or not, and a recognised label with nowhere to go -- no
    level in it, or no Control Reference yet. A third cell IN FRONT is
    harmless; the last two still read. `ledger` records each row's outcome
    so the partition can be tested against the input.

    **Page furniture is one cell too, if SSRS puts it in a table** -- a
    report title, "Page 1 of 212", a print date. Whether it does is as
    unmeasured as the two shapes above (9b and 1d, on #273). Dropping rows
    that look like furniture would be a guess that fails silently, so none
    is dropped: `_looks_like_furniture` only CLASSIFIES, the warning keeps
    the whole count and says how it splits, and the excerpts are drawn from
    the unclassified rows first. Furniture is recognised by recurring: text
    that appears on more than one row once its numbers are masked ("3 of
    12", "Page 3/12", "- 3 -", a title), plus "Page N" and a dated print
    line. **A footer shape seen only once, or furniture that does not recur,
    is still unclassified and can still take an excerpt slot** -- this
    orders what is shown, it does not guarantee it. A misclassified
    continuation is still counted; it is only shown later.
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

    skipped_text: list[str] = []
    discarded: list[tuple[str, str]] = []
    misplaced: list[list[str]] = []
    unknown: list[tuple[str, str]] = []
    orphaned: list[tuple[str, str]] = []

    def outcome(kind: str, cells: list[str]) -> None:
        if ledger is not None:
            ledger.append((kind, cells))

    for row in rows:
        cells = [cell for cell in row if cell.strip()]
        if not cells:
            continue  # a spacer row carries nothing, so it is not a row of text
        if len(cells) < _LABEL_VALUE_WIDTH:
            if hitrust.field_for_label(cells[0]) is not None:
                outcome(QUIET, cells)  # a bare label: a field left empty
            else:
                skipped_text.append(cells[0])
                outcome(REPORTED, cells)
            continue
        label, value = cells[-2], cells[-1]
        field = hitrust.field_for_label(label)
        level = hitrust.level_from_label(label)

        if field in ("category", "objective", "objective_statement"):
            setattr(context, field, value)
            current.clear()
            outcome(PLACED, cells)
            continue
        if field == "reference":
            context.reference = value
            context.specification = ""
            context.factor_type = ""
            current.clear()
            outcome(PLACED, cells)
            continue
        if field in ("specification", "factor_type"):
            setattr(context, field, value)
            outcome(PLACED, cells)
            continue
        if field in (
            "statement",
            "organizational_factors",
            "system_factors",
            "regulatory_factors",
            "mapping",
        ):
            if level and context.reference:
                lost = _absorb(record_for(level), field, value)
                if lost:
                    discarded.append((f"{context.reference} {level}", lost))
                outcome(PLACED, cells)
            else:
                # Recognised, and then nowhere to put it: no level in the
                # label ("Implementation:"), or no Control Reference yet.
                # This `continue` dropped text silently until 1d measured it
                # on #281 -- a guard that drops a recognised row reports it.
                orphaned.append((label, value))
                outcome(REPORTED, cells)
            continue
        if field in _KNOWN_UNREAD:
            outcome(QUIET, cells)  # a label this reader knows and does not keep
            continue
        if field is None and level and hitrust.field_for_label(value) is not None:
            # A level heading: "Level 1 | Implementation Requirements". Both
            # cells are captions, so no requirement text is in the row.
            outcome(QUIET, cells)
            continue

        # Nothing placed this row and it is in no quiet set, so it is
        # REPORTED by default: a new shape fails loud rather than vanishing
        # (#277, #281). The parse is unchanged.
        if any(hitrust.field_for_label(cell) is not None for cell in cells[:-2]):
            # A recognised label that is not second-to-last: read as (text,
            # extra cell), so its value AND the level record it would have
            # opened are both gone.
            misplaced.append(cells)
        else:
            unknown.append((label, value))
        outcome(REPORTED, cells)

    if losses is not None:
        losses.extend(_describe_losses(skipped_text, discarded, misplaced, unknown, orphaned))
    return records


def _excerpt(text: str, width: int = 70) -> str:
    text = " ".join(text.split())
    return text if len(text) <= width else text[: width - 3] + "..."


#: Single-cell text that is probably page furniture: a page number, or a
#: "printed on <date>" line. Deliberately narrow -- this only decides the
#: ORDER excerpts are shown in, never whether a row counts -- and it needs a
#: real date, because "run ... every 30 days" is how a requirement reads.
_FURNITURE_RE = re.compile(
    r"^(?:page\s+\d+(?:\s+of\s+\d+)?"
    r"|.*\b(?:printed|generated|run|created)\s+(?:on|at)\s+\S*\d{1,4}[/.-]\d{1,2}[/.-]\d{1,4}.*)$",
    re.IGNORECASE,
)


def _template(text: str) -> str:
    """`text` with every run of digits masked, so "3 of 12" and "4 of 12"
    are one template -- a footer recurs with only its number changing."""
    return re.sub(r"\d+", "#", " ".join(text.split()))


def _looks_like_furniture(text: str, occurrences: int) -> bool:
    """A page number or print line, or text whose digit-masked template
    recurs on more than one row -- a title or a numbered footer on every
    page (1d, on #273). A continuation is part of one requirement's text,
    so it has no reason to recur; two continuations differing ONLY in their
    numbers would be classed as furniture, and are still counted."""
    return occurrences > 1 or bool(_FURNITURE_RE.match(" ".join(text.split())))


def _describe_losses(
    skipped_text: list[str],
    discarded: list[tuple[str, str]],
    misplaced: list[list[str]] | None = None,
    unknown: list[tuple[str, str]] | None = None,
    orphaned: list[tuple[str, str]] | None = None,
) -> list[str]:
    """Warnings for what `records_from_pairs` could not place, first three shown.

    Skipped rows are classified, never filtered: the count is the total, and
    the split says how many look like page furniture. Excerpts come from the
    rest first, so the rows most likely to be lost requirement text are the
    ones a reader sees."""
    notes = []
    if skipped_text:
        seen: dict[str, int] = {}
        for text in skipped_text:
            seen[_template(text)] = seen.get(_template(text), 0) + 1
        furniture = [s for s in skipped_text if _looks_like_furniture(s, seen[_template(s)])]
        other = [s for s in skipped_text if not _looks_like_furniture(s, seen[_template(s)])]
        shown = (other + furniture)[:3]
        notes.append(
            f"{len(skipped_text)} row(s) of text had no label and were skipped "
            f"({len(other)} unclassified, {len(furniture)} look like page numbers, "
            "print dates or repeated titles). If any continues a requirement across "
            "a page break, that text is NOT in the catalog: "
            + "; ".join(repr(_excerpt(s)) for s in shown)
        )
    if discarded:
        notes.append(
            f"{len(discarded)} statement(s) arrived as two different copies; the "
            "longer was kept and the shorter is NOT in the catalog: "
            # Truncate the lost text, never the location: a prefix inside the
            # excerpt once left ~30 characters of what was actually lost.
            + "; ".join(f"{where}: {_excerpt(lost)!r}" for where, lost in discarded[:3])
        )
    if misplaced:
        notes.append(
            f"{len(misplaced)} row(s) had more than two cells with the label not "
            "second-to-last, so nothing read them: their text, and any level "
            "record they would have opened, is NOT in the catalog: "
            + "; ".join(repr(_excerpt(" | ".join(cells))) for cells in misplaced[:3])
        )
    if unknown:
        notes.append(
            f"{len(unknown)} row(s) had a label this reader does not recognise, so "
            "their text is NOT in the catalog: "
            + "; ".join(f"{_excerpt(label)!r}: {_excerpt(value)!r}" for label, value in unknown[:3])
        )
    if orphaned:
        notes.append(
            f"{len(orphaned)} row(s) had a recognised label but no level in it, or came "
            "before any Control Reference, so their text is NOT in the catalog: "
            + "; ".join(
                f"{_excerpt(label)!r}: {_excerpt(value)!r}" for label, value in orphaned[:3]
            )
        )
    return notes


def _absorb(record: Record, field: str, value: str) -> str:
    """Fold a value into a record that may already hold part of it, and
    return any text that was discarded doing so (`""` when nothing was).

    **Assumed, not measured** (#266): that SSRS breaks a long cell across a
    page boundary and re-prints its label on the next page, so one
    requirement's mapping list can arrive as two rows. Overwriting would
    keep only the tail, so list-shaped fields are concatenated.

    **Also assumed, and measured to lose text where it fails:** that a
    statement is one paragraph and never split. A statement keeps whichever
    copy is longer, so if one IS split -- label reprinted, exactly the shape
    above -- the shorter half is discarded. It is returned so the caller can
    report it. Keeping the longer copy is unchanged, because concatenating
    would change the catalog built from a customer's file on a guess about
    a format nobody here has seen. An identical copy, or one contained in
    the other, discards nothing.
    """
    existing = getattr(record, field)
    if not existing:
        setattr(record, field, value)
        return ""
    if field == "statement":
        if value in existing:
            return ""
        if existing in value:
            setattr(record, field, value)
            return ""
        if len(value) > len(existing):
            setattr(record, field, value)
            return existing
        return value
    if value not in existing:
        setattr(record, field, existing + "\n" + value)
    return ""


def records_from_markup(markup: str, losses: list[str] | None = None) -> list[Record]:
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

    records = records_from_pairs(rows, losses)
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


def read_records(path: Path, losses: list[str] | None = None) -> list[Record]:
    """Read any supported HITRUST export into records.

    `losses` collects what a rendered report could not place; see
    `records_from_pairs`. The CSV and workbook readers have no such case.
    """
    suffix = path.suffix.lower()
    if suffix in CSV_SUFFIXES:
        header, rows = read_csv(path)
        return records_from_table(header, rows)
    if suffix in WORKBOOK_SUFFIXES:
        header, rows = read_workbook(path)
        return records_from_table(header, rows)
    if suffix in MHTML_SUFFIXES:
        return records_from_markup(read_mhtml(path), losses)
    if suffix in HTML_SUFFIXES:
        return records_from_markup(path.read_text(encoding="utf-8", errors="replace"), losses)
    raise ExportFormatError(
        f"no reader for {suffix or 'a file with no extension'}. Supported: "
        + ", ".join(sorted(CSV_SUFFIXES | WORKBOOK_SUFFIXES | HTML_SUFFIXES | MHTML_SUFFIXES))
    )


def load(path: Path, *, version: str = "", losses: list[str] | None = None) -> list:
    """Read a HITRUST CSF export into `Control` objects.

    The whole BYOC path in one call: read the file, name its columns,
    deduplicate the report's repeated rows, learn the authoritative-source
    vocabulary from the mappings, and assemble one Control per control
    reference.
    """
    path = Path(path)
    records = read_records(path, losses)
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
