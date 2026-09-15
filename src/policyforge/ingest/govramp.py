"""What GovRAMP is, as distinct from the workbook it arrives in.

`govramp_export.py` reads the file. This module holds the framework.

GovRAMP (formerly StateRAMP) publishes no control catalog of its own. It is
a **profile over NIST SP 800-53 Rev 5**: it selects which 800-53 controls a
cloud service offering must meet at a given impact level, reproduces their
text verbatim, and adds two things the base catalog deliberately leaves
open.

* **Parameter values.** Where 800-53 writes `[Assignment:
  organization-defined frequency]`, GovRAMP writes `AC-1 (c) (1) [at least
  every 3 years]`. These are not suggestions and they are not ours to
  choose: for anyone seeking a GovRAMP authorization they are the answer,
  already decided, with a citation. `parameters/ledger.py` exists because
  800-53 leaves roughly 1,200 such values open; a profile answers a few
  hundred of them outright, which is most of the reason to ingest one.
* **Additional requirements and guidance.** Normative sentences layered on
  a control -- "the service provider defines the time period for non-user
  accounts" -- that exist nowhere in 800-53.

And one axis 800-53 does not have at all: the **verification tier**.

## Tiers are not impact levels, and conflating them corrupts scope

A GovRAMP matrix is published *per impact level* -- a Low, a Moderate and a
High workbook, matching the FIPS 199 categorisation of the system. Within
one workbook, three columns then say which controls are required to reach
each of GovRAMP's three verification tiers:

    Core (60 of Moderate's 319) -> Ready (80) -> Authorized (319)

Core is a subset of Ready is a subset of Authorized, and the file itself is
the only place that nesting is stated, so it is checked on the way in
rather than assumed. The two axes multiply: "Moderate Ready" and "Moderate
Authorized" are different obligations over the same catalog, and a reader
who takes the tier for a baseline concludes a service offering has 319
controls to implement when 80 stand between it and the tier it is actually
pursuing.

`Control.baseline` carries both, impact level first:
`"Moderate; Core, Ready, Authorized"`. One string because that is the field
the schema has and every consumer substring-matches it -- `--baseline
moderate` and a filter for `core` both land correctly -- and
semicolon-separated because the two halves are not the same kind of thing.

## What is deliberately not carried

The matrix scores each control with a **MITRE Control Protection Value**
(`99.64` for AC-2), and the workbook's later sheets -- the Control
Implementation Summary and the Control Responsibility Matrix -- hold one row
per control for a service provider to fill in. Neither is ingested. The
score has no consumer in this pipeline, and the CIS/CRM sheets in a blank
template carry nothing but zeros; a schema field nothing reads is clutter
that reads as data. If a consumer appears, the columns are still in the
file and `govramp_export.py` already knows how to find the sheet.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

from .schema import Control, ControlEnhancement

FRAMEWORK = "GovRAMP"

#: The base catalog a GovRAMP matrix profiles. Used as the crosswalk key so
#: `mapping/crosswalk.py` anchors every GovRAMP control on its 800-53
#: equivalent -- which, GovRAMP being a profile, is the same identifier.
NIST_SOURCE = "NIST 800-53"

CORE = "Core"
READY = "Ready"
AUTHORIZED = "Authorized"

#: Ascending rigour, and genuinely ordered: each tier's control set contains
#: the one before it. `tier_nesting_breaks` checks that against the file.
TIER_ORDER = (CORE, READY, AUTHORIZED)

LOW = "Low"
MODERATE = "Moderate"
HIGH = "High"
IMPACT_LEVELS = (LOW, MODERATE, HIGH)

#: Separates the impact level from the tier list in `Control.baseline`.
BASELINE_SEPARATOR = "; "

#: What the Rev 5 v1.06 Moderate matrix actually holds, for spotting a sheet
#: that was half-read. An observation from one real file rather than a
#: published figure, which is why only the level that has been seen is
#: listed, and why falling short of it warns instead of raising -- GovRAMP
#: revises these workbooks, and a loader that refused a catalog for growing
#: would be wrong every time it fired.
OBSERVED_CONTROL_COUNTS = {MODERATE: 319}

#: `AC-1`, `AC-2 (1)`, and the zero-padded SORT ID spelling of the same
#: control, `AC-02 (01)`. Both appear in one workbook, in adjacent columns.
#: Leading zeros are stripped rather than preserved so that `AC-02 (01)` and
#: `AC-2 (1)` resolve to one identifier; a catalog holding both spellings
#: joins to 800-53 on neither.
CONTROL_ID_RE = re.compile(
    r"^\s*([A-Za-z]{2,3})\s*-\s*0*(\d{1,3})\s*(?:\(\s*0*(\d{1,3})\s*\))?\s*$"
)

#: The SCRM family is the one whose heading ends in the word "FAMILY", an
#: artifact of the heading rather than part of the name. Left in, it makes
#: `Supply Chain Risk Management Family` -- which matches no other catalog's
#: spelling of it, so nothing joins on family name.
_FAMILY_SUFFIX_RE = re.compile(r"\s+family\s*$", re.IGNORECASE)

#: Lowercased inside a title-cased family name, to match the house style the
#: OSCAL catalog uses ("System and Communications Protection"). A family that
#: reads `System And Communications Protection` beside it looks like a
#: different family to anyone skimming a merged report.
_MINOR_WORDS = {"and", "or", "of", "the", "for", "to", "in", "a", "an", "on", "with"}

#: One bracketed value inside a parameter cell. Values never nest brackets
#: -- they nest *parentheses*, as in `[ninety (90) days]` -- so matching to
#: the first `]` is exact rather than approximate.
_BRACKET_RE = re.compile(r"\[([^\]]*)\]")

#: `Yes` as the tier columns spell it, plus the marks the summary sheets use
#: for the same thing. Anything else (a blank, a stray space, `No`) is read
#: as "not required", which is the safe direction: a control wrongly pulled
#: into Core inflates a scope somebody is assessed against.
_AFFIRMATIVE = {"yes", "y", "x", "true", "required"}


# --------------------------------------------------------------------------
# Identifiers, families, titles
# --------------------------------------------------------------------------


def parse_control_id(value: str) -> tuple[str, str]:
    """`("AC-2", "")` for a control, `("AC-2", "AC-2(1)")` for an enhancement.

    The second element is the enhancement's own identifier, empty when the
    row is a base control. Both are normalized to the spelling the OSCAL
    loader produces -- `AC-2(1)`, no space -- because a GovRAMP catalog whose
    enhancement ids read `AC-2 (1)` crosswalks to nothing: the identifier
    *is* the join key between a profile and the catalog it profiles.
    """
    match = CONTROL_ID_RE.match(value or "")
    if match is None:
        # An unparseable id is kept verbatim rather than dropped. A row that
        # reached here is a real row of the matrix, and a control missing
        # from a scope report is worse than one with an odd identifier --
        # `summarize` reports these so they are visible either way.
        return " ".join((value or "").split()), ""
    family, number, enhancement = match.groups()
    base = f"{family.upper()}-{int(number)}"
    return (base, f"{base}({int(enhancement)})") if enhancement else (base, "")


def family_abbr(control_id: str) -> str:
    """`"AC-2(1)"` -> `"AC"`."""
    return control_id.split("-")[0].strip().upper() if "-" in control_id else ""


def normalize_family(value: str) -> str:
    """`"SUPPLY CHAIN RISK MANAGEMENT FAMILY"` -> `"Supply Chain Risk Management"`.

    The matrix shouts its family names and the OSCAL catalog title-cases
    them. Both end up in one merged catalog, so they have to agree.
    """
    cleaned = _FAMILY_SUFFIX_RE.sub("", " ".join((value or "").split()))
    if not cleaned:
        return ""
    # Only reshape a heading that is shouting. A name already in mixed case
    # was written deliberately, and title-casing it would flatten an acronym.
    if not cleaned.isupper():
        return cleaned
    words = cleaned.lower().split()
    return " ".join(
        word if index and word in _MINOR_WORDS else word.capitalize()
        for index, word in enumerate(words)
    )


def split_title(value: str) -> tuple[str, str]:
    """Split a Control Name cell into (parent name, enhancement name).

    An enhancement row names its parent on the first line and itself on the
    second -- "Account Management", then "Automated System Account
    Management". The pair is returned rather than just the enhancement's own
    name so a base control row, which has only the one line, goes through
    the same call and yields an empty second element.
    """
    parts = [" ".join(line.split()) for line in (value or "").splitlines()]
    parts = [part for part in parts if part]
    if not parts:
        return "", ""
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], " ".join(parts[1:])


# --------------------------------------------------------------------------
# The parameter cell
# --------------------------------------------------------------------------


def parse_parameters(cell: str) -> dict[str, str]:
    """Pull `{citation: value}` out of a GovRAMP parameter cell.

    One parameter per line, each a citation followed by one or more
    bracketed values::

        AC-1 (c) (1) [at least every 3 years]
        AC-1 (c) (2) [at least annually] [significant changes]

    Four shapes in the published Moderate matrix need handling, all of them
    real rather than defensive:

    * **Several values on one line.** Joined with "; " -- `AC-1 (c) (2)` is
      one decision with two halves, and splitting it into two entries would
      claim the second overrides the first.
    * **A continuation line carrying no citation** (`AC-2 (2)`'s second
      line), which belongs to the citation above it. Read as an entry of its
      own it would key on the empty string and overwrite its neighbour.
    * **No space before the bracket**: `AC-2 (12) (b)[at a minimum...]`.
    * **A trailing note outside the brackets**: "(See additional
      requirements and guidance.)". Kept, appended to the value -- it points
      at text this loader also captures, and dropping it severs the link.

    Returns an empty dict for an empty cell, which most rows have: only 137
    of the Moderate matrix's 319 controls define a parameter at all.
    """
    values: dict[str, str] = {}
    last_citation = ""

    for raw_line in (cell or "").splitlines():
        line = " ".join(raw_line.split())
        if not line:
            continue

        brackets = list(_BRACKET_RE.finditer(line))
        if not brackets:
            # A line with no bracketed value is prose about the parameter
            # above it rather than a parameter of its own.
            if last_citation:
                values[last_citation] = f"{values[last_citation]} {line}".strip()
            continue

        citation = line[: brackets[0].start()].strip() or last_citation
        if not citation:
            continue

        parts = [" ".join(m.group(1).split()) for m in brackets]
        value = "; ".join(part for part in parts if part)
        remainder = line[brackets[-1].end() :].strip()
        if remainder:
            value = f"{value} {remainder}".strip()

        # A citation seen twice (the continuation case) extends rather than
        # replaces: both lines describe one parameter.
        if citation in values:
            values[citation] = f"{values[citation]}; {value}".strip("; ")
        else:
            values[citation] = value
        last_citation = citation

    return values


# --------------------------------------------------------------------------
# Rows
# --------------------------------------------------------------------------


@dataclass
class Row:
    """One line of the controls matrix, before it becomes a Control.

    Verbatim except for the tier flags, which are booleans because
    `"Yes"`/`"No"` is a spelling of a boolean and every consumer would
    otherwise re-derive it.
    """

    control_id: str = ""
    sort_id: str = ""
    family: str = ""
    name: str = ""
    statement: str = ""
    discussion: str = ""
    parameters: str = ""
    additional_requirements: str = ""
    #: `{tier name: required}`, keyed by the `TIER_ORDER` names.
    tiers: dict[str, bool] = field(default_factory=dict)

    @property
    def is_populated(self) -> bool:
        """A row with no identifier is a spacer, the totals line, or part of
        the blank tail every one of these workbooks carries. Not an error,
        and not a control."""
        return bool(self.control_id.strip())


def is_affirmative(value: str) -> bool:
    return " ".join(str(value or "").split()).lower() in _AFFIRMATIVE


def required_tiers(row: Row) -> list[str]:
    """The tiers a row is required for, in ascending order of rigour."""
    return [tier for tier in TIER_ORDER if row.tiers.get(tier)]


def baseline_label(impact_level: str, tiers: list[str]) -> str:
    """`"Moderate; Core, Ready, Authorized"`.

    Either half may be missing -- an export whose tier columns were not
    found still knows its impact level, and is more useful labelled with
    half the answer than with none.
    """
    halves = [part for part in (impact_level, ", ".join(tiers)) if part]
    return BASELINE_SEPARATOR.join(halves)


def tier_nesting_breaks(rows: list[Row]) -> list[str]:
    """Controls required at a tier but not at the stricter tier above it.

    Empty for an intact matrix, because GovRAMP's tiers nest. It is checked
    rather than trusted because the failure it catches is otherwise silent:
    if the three tier columns are misidentified -- swapped with each other,
    or shifted one column onto `SORT ID` -- every count still looks
    plausible and every scope built on them is wrong.
    """
    broken: list[str] = []
    for row in rows:
        marked = [tier for tier in TIER_ORDER if row.tiers.get(tier)]
        if not marked:
            continue
        from_lowest = TIER_ORDER[TIER_ORDER.index(marked[0]) :]
        missing = [tier for tier in from_lowest if not row.tiers.get(tier)]
        if missing:
            broken.append(f"{row.control_id} ({', '.join(marked)} but not {', '.join(missing)})")
    return broken


# --------------------------------------------------------------------------
# Assembly
# --------------------------------------------------------------------------


def build_controls(
    rows: list[Row],
    *,
    impact_level: str = "",
    version: str = "",
    source_path: str = "",
) -> list[Control]:
    """Assemble matrix rows into `Control` objects.

    Enhancement rows fold into their parent as `ControlEnhancement`, which
    is the schema's *additive* sub-requirement and exactly what an 800-53
    enhancement is: AC-2(1) is AC-2 and something more, and an assessor
    reads both. (Contrast `Requirement`, which HITRUST needs because its
    levels are *alternatives*. Modelling these as requirements would
    double-count every enhanced control in a coverage report.)

    An enhancement whose base control is absent gets a parent shell carrying
    the family and the parent's name. The published Moderate matrix has no
    such rows -- 800-53 does not select an enhancement without its base --
    but a filtered or hand-trimmed export easily does, and the alternative
    is dropping the row.

    Row order is preserved, which in these workbooks is catalog order.
    """
    controls: dict[str, Control] = {}
    order: list[str] = []

    def control_for(base_id: str, row: Row, parent_name: str) -> Control:
        if base_id not in controls:
            order.append(base_id)
            controls[base_id] = Control(
                control_id=base_id,
                title=parent_name,
                framework=FRAMEWORK,
                framework_version=version,
                family=normalize_family(row.family),
                family_abbr=family_abbr(base_id),
                # A profile's identifiers are the base catalog's, so the
                # crosswalk edge is the identifier itself. This one line is
                # what makes `policyforge map` cross GovRAMP with NIST.
                source_crosswalk={NIST_SOURCE: base_id},
                source_path=source_path or None,
            )
        return controls[base_id]

    for row in rows:
        if not row.is_populated:
            continue

        base_id, enhancement_id = parse_control_id(row.control_id)
        parent_name, own_name = split_title(row.name)
        baseline = baseline_label(impact_level, required_tiers(row))
        parameters = parse_parameters(row.parameters)
        additional = "\n".join(
            line.strip()
            for line in (row.additional_requirements or "").splitlines()
            if line.strip()
        )

        control = control_for(base_id, row, parent_name)

        if not enhancement_id:
            # A base row is the authority on its own control. Assigned
            # rather than merged, because a parent shell may already have
            # been created by an earlier enhancement row holding only a name.
            control.title = parent_name or control.title
            control.baseline = baseline
            control.control_statement = " ".join((row.statement or "").split())
            control.discussion = " ".join((row.discussion or "").split())
            control.parameter_values = parameters
            control.additional_requirements = additional
            control.family = control.family or normalize_family(row.family)
            continue

        control.enhancements.append(
            ControlEnhancement(
                enhancement_id=enhancement_id,
                title=own_name or parent_name,
                baseline=baseline,
                description=" ".join((row.statement or "").split()),
                source_crosswalk={NIST_SOURCE: enhancement_id},
                parameter_values=parameters,
                additional_requirements=additional,
            )
        )

    return [controls[key] for key in order]


# --------------------------------------------------------------------------
# Reporting
# --------------------------------------------------------------------------


@dataclass
class Summary:
    """What a parse found, and what looks wrong with it.

    Worth printing after every parse. A heuristic loader does not fail by
    raising; it fails by returning a plausible catalog with one column
    missing, and only the counts show that.
    """

    impact_level: str = ""
    version: str = ""
    controls: int = 0
    enhancements: int = 0
    families: int = 0
    #: `{tier: items required}`, counting enhancements alongside controls
    #: since a tier's scope includes both.
    tiers: Counter = field(default_factory=Counter)
    parameters: int = 0
    items_with_parameters: int = 0
    guidance_blocks: int = 0
    unparsed_ids: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def format_report(self) -> str:
        label = " ".join(part for part in (FRAMEWORK, self.version, self.impact_level) if part)
        lines = [
            label,
            f"  {self.controls} controls, {self.enhancements} enhancements, "
            f"{self.families} families",
        ]
        if self.tiers:
            lines.append("  Required per tier (controls and enhancements):")
            lines.extend(
                f"    {tier:<11} {self.tiers[tier]}" for tier in TIER_ORDER if tier in self.tiers
            )
        lines.append(
            f"  {self.parameters} GovRAMP-defined parameter values across "
            f"{self.items_with_parameters} controls/enhancements"
        )
        lines.append(f"  {self.guidance_blocks} additional requirement/guidance blocks")
        if self.unparsed_ids:
            shown = ", ".join(self.unparsed_ids[:5])
            more = f" (+{len(self.unparsed_ids) - 5} more)" if len(self.unparsed_ids) > 5 else ""
            lines.append(f"  Identifiers of unrecognised shape, kept verbatim: {shown}{more}")
        lines.extend(f"  WARNING: {warning}" for warning in self.warnings)
        return "\n".join(lines)


def summarize(controls: list[Control], *, rows: list[Row] | None = None) -> Summary:
    """Describe a parsed catalog, and say when it looks incomplete.

    `rows` is optional and adds only the tier-nesting check, which needs the
    flat rows rather than the assembled tree.
    """
    summary = Summary()
    summary.controls = len(controls)
    summary.families = len({c.family for c in controls if c.family})

    if controls:
        summary.version = controls[0].framework_version
        head = (controls[0].baseline or "").split(BASELINE_SEPARATOR)[0]
        summary.impact_level = head if head in IMPACT_LEVELS else ""

    for control in controls:
        summary.enhancements += len(control.enhancements)
        if not CONTROL_ID_RE.match(control.control_id):
            summary.unparsed_ids.append(control.control_id)

        for item in (control, *control.enhancements):
            for tier in TIER_ORDER:
                if tier in (item.baseline or ""):
                    summary.tiers[tier] += 1
            summary.parameters += len(item.parameter_values)
            summary.items_with_parameters += 1 if item.parameter_values else 0
            summary.guidance_blocks += 1 if item.additional_requirements else 0

    expected = OBSERVED_CONTROL_COUNTS.get(summary.impact_level)
    total = summary.controls + summary.enhancements
    if expected and total < expected * 0.6:
        summary.warnings.append(
            f"{total} controls and enhancements parsed, against {expected} in the "
            f"Rev 5 v1.06 {summary.impact_level} matrix -- this looks like a "
            "partial read rather than a smaller baseline."
        )
    if controls and not summary.tiers:
        summary.warnings.append(
            "no control is marked required for any tier, so the Core/Ready/"
            "Authorized columns were not found -- every scope built on this "
            "catalog would come back empty."
        )
    if controls and not summary.parameters:
        summary.warnings.append(
            "no GovRAMP-defined parameter values parsed. A GovRAMP matrix "
            "defines several hundred; without them this catalog is 800-53 "
            "with a baseline column, which you already have."
        )
    if controls and not summary.enhancements:
        summary.warnings.append(
            "no enhancements parsed, which no GovRAMP baseline is without -- "
            "the ID column may have been misidentified."
        )

    breaks = tier_nesting_breaks([r for r in (rows or []) if r.is_populated])
    if breaks:
        shown = "; ".join(breaks[:3])
        summary.warnings.append(
            f"{len(breaks)} control(s) required at a tier but not at the stricter "
            f"tier above it, which GovRAMP's tiers should not allow: {shown}. "
            "The tier columns may be misaligned."
        )
    return summary


__all__ = [
    "AUTHORIZED",
    "CORE",
    "FRAMEWORK",
    "IMPACT_LEVELS",
    "READY",
    "TIER_ORDER",
    "Row",
    "Summary",
    "baseline_label",
    "build_controls",
    "family_abbr",
    "is_affirmative",
    "normalize_family",
    "parse_control_id",
    "parse_parameters",
    "required_tiers",
    "split_title",
    "summarize",
    "tier_nesting_breaks",
]
