"""SOC 2: the AICPA's Trust Services Criteria, bring-your-own (#410).

**Licensed, never bundled, never fetched** (the user's decision on #410,
"Proceed as BYOC, local-only", and 80's product rules). The criteria are the
AICPA's, under its terms; this reads only the user's own copy, a text export
they make from the PDF they obtained themselves (80's ruling (b): no PDF
parser, so the project never parses the licensed document). Nothing here
touches aicpa-cima.com.

**Built and tested only against SYNTHETIC input.** No session has held a real
copy, so the grammar below is written from the shape the AICPA is publicly
known to use (a series prefix and a numbered criterion: `CC1.1`, `A1.2`,
`PI1.3`, `C1.1`, `P1.1`), and nothing is pinned from a count anyone read.
**The first real run is the user's**, and it fails loudly and whole, never
partially, if their file is shaped differently: every line that starts like
a criterion id must parse, ids are unique, and numbering within each group
(`CC1.1`, `CC1.2`, ...) runs contiguously from 1, so a dropped criterion in
the middle of a group is refused rather than silently missing. The counts
the file itself yields are reported, not checked against a number, because
there is no number anyone may know.

**A user-supplied mapping to 800-53** (the AICPA's, dated 2020-01-22, before
Rev 5 final) is read from the user's own workbook. Its columns are found by
their headings. Every link is `source-untyped` (80's ruling 1): partial, a
person's call. Every mapped 800-53 id is resolved against the shipped Rev 5
catalog: one NIST marks as changed substantively since Rev 4 is flagged in
NIST's words; one withdrawn in Rev 5 is refused and named; one that is no
Rev 5 id at all is refused and named. Nothing is remapped.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass, field

from policyforge.ingest.schema import Control

#: The name tags and reports carry. Keyed `aicpa-tsc` by the
#: "trust services criteria" needle in `mapping/crosswalk.py`.
FRAMEWORK = "AICPA Trust Services Criteria"
#: The date the AICPA gives its TSC-to-800-53 mapping (5b, on #410).
MAPPING_DATE = "2020-01-22"
CROSSWALK_SOURCE = f"AICPA TSC to NIST SP 800-53 mapping ({MAPPING_DATE})"

#: A criterion id at the start of a line: a series of one or two capitals,
#: a group number and a criterion number. `CC1.1`, `A1.2`, `PI1.3`.
_CRITERION = re.compile(
    r"^(?P<id>(?P<series>[A-Z]{1,2})(?P<group>\d{1,2})\.(?P<number>\d{1,2}))\b\s*(?P<rest>.*)$"
)
#: A line that STARTS like an id but is not one (`CC1.`, `CC1-1`, `CC 1.1`):
#: refused by name, since a parser that skipped it would drop a criterion.
_ID_LIKE = re.compile(r"^(?:[A-Z]{1,2}\s?\d{1,2}[.\-]\d{0,2}|[A-Z]{1,2}\d{1,2}\.)(?=\W|$)")


class TscError(ValueError):
    """The user's file is not shaped as this parser expects. Nothing is written."""


@dataclass
class Parsed:
    controls: list[Control]
    #: Lines before the first criterion, kept out of the catalog and counted.
    preamble_lines: int = 0
    series: dict[str, int] = field(default_factory=dict)


def parse_criteria(text: str, *, version: str) -> Parsed:
    """The criteria in the user's text export, one Control each.

    A criterion's first line after its id is its statement; the lines that
    follow, up to the next id, are its points of focus (kept as the
    control's `discussion`, one per line, in order).
    """
    blocks: list[tuple[re.Match, list[str]]] = []
    preamble = 0
    for number, raw in enumerate(text.splitlines(), start=1):
        line = " ".join(raw.split())
        if not line:
            continue
        match = _CRITERION.match(line)
        if match:
            blocks.append((match, []))
        elif _ID_LIKE.match(line):
            raise TscError(
                f"line {number} starts like a criterion id but is not one: {line[:40]!r}. "
                "Refusing rather than dropping it."
            )
        elif blocks:
            blocks[-1][1].append(line)
        else:
            preamble += 1
    if not blocks:
        raise TscError("No criterion ids (e.g. CC1.1) found at the start of any line.")

    controls, seen = [], set()
    groups: dict[tuple[str, int], list[int]] = {}
    for match, lines in blocks:
        cid = match.group("id")
        if cid in seen:
            raise TscError(f"{cid} appears twice. Refusing.")
        seen.add(cid)
        statement = match.group("rest") or (lines.pop(0) if lines else "")
        if not statement:
            raise TscError(f"{cid} has no text. Refusing.")
        groups.setdefault((match.group("series"), int(match.group("group"))), []).append(
            int(match.group("number"))
        )
        controls.append(
            Control(
                control_id=cid,
                title=statement[:120],
                framework=FRAMEWORK,
                framework_version=version,
                family=f"{match.group('series')}{match.group('group')}",
                family_abbr=match.group("series"),
                control_statement=statement,
                discussion="\n".join(lines),
            )
        )
    for (series, group), numbers in sorted(groups.items()):
        if sorted(numbers) != list(range(1, len(numbers) + 1)):
            raise TscError(
                f"{series}{group}.x criteria are numbered {sorted(numbers)}, not 1 to "
                f"{len(numbers)} without a gap. A criterion is missing or misread; refusing."
            )
    series: dict[str, int] = {}
    for control in controls:
        series[control.family_abbr] = series.get(control.family_abbr, 0) + 1
    return Parsed(controls=controls, preamble_lines=preamble, series=series)


# ---- the user's mapping to 800-53 ---------------------------------------------

_CONTROL = re.compile(r"^([A-Z]{2})-0*(\d+)(?:\s*\(0*(\d+)\))?$")


def _normalise(target: str) -> str | None:
    match = _CONTROL.match(target.strip())
    if not match:
        return None
    family, number, enhancement = match.groups()
    return f"{family}-{number}" + (f"({enhancement})" if enhancement else "")


@dataclass
class Mapping:
    #: {criterion id: [800-53 ids]}, every one a Rev 5 id.
    links: dict[str, list[str]] = field(default_factory=dict)
    #: {800-53 id: NIST's label}, for every linked id NIST marks as changed.
    flagged: dict[str, str] = field(default_factory=dict)
    #: (criterion, target, reason) for each link refused by name.
    refused: list[tuple[str, str, str]] = field(default_factory=list)


def parse_mapping(
    raw: bytes, *, criteria: set[str], rev5_ids: set[str], changed: dict[str, bool]
) -> Mapping:
    """The user's TSC-to-800-53 workbook, resolved against Rev 5.

    The criterion and 800-53 columns are found by heading, on whichever sheet
    has both: exactly one such sheet and one of each column, or the parse is
    refused. A cell may list several ids, separated by commas, semicolons or
    line breaks.
    """
    import openpyxl

    from policyforge.ingest import nist_rev4_rev5

    book = openpyxl.load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
    found = []
    for sheet in book.worksheets:
        rows = list(sheet.iter_rows(values_only=True))
        for index, row in enumerate(rows[:10]):
            cells = [" ".join(str(c or "").lower().split()) for c in row]
            tsc = [
                i
                for i, c in enumerate(cells)
                if "tsc" in c or "trust services" in c or c in ("criteria", "criterion")
            ]
            nist = [i for i, c in enumerate(cells) if "800-53" in c]
            if tsc and nist:
                found.append((sheet.title, rows, index, tsc, nist))
                break
    if len(found) != 1:
        raise TscError(
            f"{len(found)} sheets have both a TSC column and an 800-53 column heading; "
            "expected exactly one. Refusing."
        )
    title, rows, header, tsc, nist = found[0]
    if len(tsc) != 1 or len(nist) != 1:
        raise TscError(
            f"Sheet {title!r} has {len(tsc)} TSC and {len(nist)} 800-53 column headings; "
            "expected one of each. Refusing."
        )
    mapping = Mapping()
    for row in rows[header + 1 :]:
        criterion = " ".join(str(row[tsc[0]] or "").split())
        if not criterion:
            continue
        match = _CRITERION.match(criterion)
        if not match or match.group("id") not in criteria:
            raise TscError(
                f"The mapping names criterion {criterion[:30]!r}, which your criteria file does "
                "not have. Refusing: a link with nowhere to go would be dropped."
            )
        cid = match.group("id")
        for target in re.split(r"[,;\n]+", str(row[nist[0]] or "")):
            if not target.strip():
                continue
            control = _normalise(target)
            if control is None:
                mapping.refused.append((cid, target.strip(), "not an 800-53 id"))
                continue
            label = nist_rev4_rev5.label(control, changed, rev5_ids)
            if label == nist_rev4_rev5.WITHDRAWN:
                mapping.refused.append((cid, control, label))
                continue
            if control not in rev5_ids:
                mapping.refused.append((cid, control, "not an id of SP 800-53 Rev 5"))
                continue
            if label:
                mapping.flagged[control] = label
            ids = mapping.links.setdefault(cid, [])
            if control not in ids:
                ids.append(control)
    return mapping


def attach(controls: list[Control], mapping: Mapping) -> None:
    """Put the mapping's links on the criteria, under the 800-53 key."""
    from policyforge.ingest.oscal_loader import CROSSWALK_KEY_800_53

    for control in controls:
        if control.control_id in mapping.links:
            control.source_crosswalk[CROSSWALK_KEY_800_53] = ", ".join(
                mapping.links[control.control_id]
            )
