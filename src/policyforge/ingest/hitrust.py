"""What HITRUST CSF *is*, independent of the file it arrived in.

Every other framework this project reads has one canonical machine-readable
form -- OSCAL JSON for 800-53, the eCFR API for HIPAA. HITRUST has none.
What people actually have is a MyCSF report export, and MyCSF renders its
reports through SQL Server Reporting Services, which means the column
headers of a CSV export are SSRS textbox names: `Textbox52`, `Textbox105`,
`Textbox47`. They carry no meaning, they are not stable across report
versions, and two people on two CSF releases will hand you two different
sets of them. The same report saved as MHTML carries the *human* labels
instead ("Control Reference:", "Level 1 Implementation:") because that is
what a reader sees.

So this module holds the part that does not change -- the shape of the
framework -- and leaves the part that does (which column is which) to
`detect_fields`, which tries labels first and falls back to recognising
columns by what their values look like.

## The hierarchy

Four tiers, and the middle one is easy to miss::

    Control Category        14    "01.0 - Access Control"
      Control Objective     49    "01.01 Business Requirement for Access Control"
        Control Reference  156    "01.a Access Control Policy"
          Requirement     ~1200   one per (reference x level)

Counts are from CSF v11.7 and are not assertions -- HITRUST adds references
between releases. They are here so that a loader returning 12 controls from
a full library export looks as wrong as it is.

A **Control Reference** is what maps to this project's `Control`: it has an
id, a title, and a one-paragraph *Control Specification* that reads like a
policy statement. It is not, however, what an assessor grades you against.

## Levels are alternatives, not enhancements

Under each reference sit **requirement statements**, one per level, and
"level" spans two different things that a CSF export writes into one
column:

* **Maturity levels** -- `Level 1`, `Level 2`, `Level 3`. An ordered
  ladder. Every reference has a Level 1; roughly a third carry all three.
* **Overlays** -- `Level HIPAA`, `Level FedRAMP`, `Level CMS`, `Level FTI
  Custodians`, `Level GDPR`, `Level PCI`, `Level NYDOH`, and sixty-odd
  more. Unordered, named for the authority that compels them, and switched
  on by a regulatory or segment scoping factor rather than by ambition.

Which levels apply is computed from **scoping factors** -- organizational
(bed count, covered lives, records held), system (internet-accessible?),
and regulatory (do you handle federal tax information?). This is why
`Requirement` is not `ControlEnhancement`: an 800-53 enhancement adds
rigour to a control everyone shares, while two HITRUST-assessed
organizations under the same reference may be graded on entirely different
sentences.

## The crosswalk is the valuable part

Each requirement statement carries a **Control Standard Mapping**: a list
of `<authoritative source> <identifier>` strings, tens of thousands of them
in a full library. HITRUST has already done the reconciliation this project
otherwise does by hand, and four of its sources -- NIST SP 800-53, the
HIPAA Security Rule, CMS ARC-AMPE, FedRAMP -- are catalogs PolicyForge
already bundles. Parsing it well is most of the value of ingesting HITRUST
at all.

The strings have no delimiter between source and identifier, and both
halves contain spaces, digits and punctuation::

    NIST SP 800-53 r5 PL-11
    ISO/IEC 27001:2022 4.3d
    NY DoH Title 10 Section 405.46 (d)(3)(x)
    The Joint Commission (v2016) TJC IM.02.01.03, EP 1

No regex splits those. `learn_sources` instead learns the source vocabulary
from the export itself by branching frequency -- a source name is a token
prefix after which many different things follow -- which means it works on
next year's sources without anybody updating a list here, and never needs a
copy of HITRUST's source list committed to this repository.

## Report artifacts to strip

A MyCSF CSV export is a rendered report, not a dataset, and carries three
kinds of noise this module removes:

1. **Duplicate rows.** v11.7 exports 2,818 rows for 1,219 real records --
   whole rows repeated verbatim by a join the report does not render.
   Deduplication is mandatory rather than tidy: without it every coverage
   and mapping count is inflated by a factor that varies per control.
2. **Restated labels.** Several columns hold only "Level 2 Organizational
   Factors:" -- the caption SSRS printed beside the value. They are
   derivable from the level and carry nothing.
3. **Truncation.** The level column is cut at 36 characters, so long
   overlay names arrive clipped ("Level Digital Personal Data Protecti").
   The caption columns and the MHTML rendering keep the full name, so
   `merge_level_names` recovers it where a longer form is present.

Licence note: nothing here embeds HITRUST content. The vocabulary is
learned at parse time from the user's own licensed export, and this module
never writes anything to disk.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from .schema import MATURITY, OVERLAY, Control, Requirement

FRAMEWORK = "HITRUST-CSF"

#: Shape of a full CSF library export, for sanity-checking a parse. Soft
#: expectations: HITRUST grows these between releases, so a mismatch is
#: worth reporting and never worth raising on.
EXPECTED = {"categories": 14, "objectives": 49, "references": 156}

#: `01.a Access Control Policy`, `00.a Information Security Management
#: Program`, `09.aa Audit Logging`. Digits, a dot, one or two letters.
REFERENCE_RE = re.compile(r"^\s*(\d{1,2}\.[a-z]{1,2})\s+(.*\S)?\s*$")

#: `01.01 Business Requirement for Access Control`, `0.01 ...`.
OBJECTIVE_RE = re.compile(r"^\s*(\d{1,2}\.\d{2})(?![\d.])\s+(.*\S)?\s*$")

#: `01.0 - Access Control`. The separator is a dash here and whitespace in
#: the other two tiers, which is a report convention rather than a rule, so
#: both are accepted.
#:
#: The lookahead is what keeps a category from swallowing an objective:
#: without it `01.0` matches the opening of `01.01 Business Requirement for
#: Access Control`, and column detection then reads the objective column as
#: the category column and collapses 49 objectives into 14.
# The en dash is deliberate: SSRS renders the category separator as one.
CATEGORY_RE = re.compile(r"^\s*(\d{1,2}\.0)(?![\d.])\s*[-–]?\s*(.*\S)?\s*$")  # noqa: RUF001

LEVEL_RE = re.compile(r"^\s*Level\s+(\S.*?)\s*$", re.IGNORECASE)

#: Only these three are the maturity ladder. Everything else under `Level `
#: is an overlay, and treating an unrecognised level as an overlay is the
#: safe default: a new regulatory level read as maturity would silently
#: join an ordered scale it has no place on.
MATURITY_NAMES = {"1", "2", "3"}

#: Where the level column is cut in an SSRS CSV export.
LEVEL_TRUNCATION = 36

#: Canonical field names, and the labels an export is known to use for
#: them. Matched case- and punctuation-insensitively, after any "Level N"
#: prefix is stripped, so "Level 2 Implementation:" and "Level FedRAMP
#: Implementation:" both resolve to `statement`.
FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "category": ("control category", "category"),
    "objective": ("objective name", "objective"),
    "objective_statement": ("control objective", "objective description"),
    "reference": ("control reference", "reference", "control name"),
    "specification": ("control specification", "specification", "control text"),
    "factor_type": ("factor type", "type"),
    "topics": ("topics", "topic"),
    "level": ("level", "implementation level"),
    "statement": (
        "implementation",
        "implementation requirements",
        "requirement statement",
        # A CSV export names this column `Level_Implementation`, which
        # normalizes to two words with no level between them and so escapes
        # the "Level N Implementation:" stripping below.
        "level implementation",
    ),
    "organizational_factors": ("organizational factors", "organisational factors"),
    "system_factors": ("system factors",),
    "regulatory_factors": ("regulatory factors",),
    "mapping": ("control standard mapping", "standard mapping", "mapping"),
}

_PUNCT_RE = re.compile(r"[^a-z0-9 ]+")
_LEVEL_FACTORS_RE = re.compile(
    r"^level\s+.*?\s+(?=(?:organizational|organisational|system|regulatory)\b)"
)
_LEVEL_FIELD_RE = re.compile(r"^level\s+.*?\s+(?=(?:implementation|control standard)\b)")


def _normalize_label(label: str) -> str:
    """Reduce an export's label to something comparable with an alias."""
    text = " ".join(str(label or "").split()).lower().rstrip(":")
    # "level 2 organizational factors" -> "organizational factors"; the
    # level is data, not part of the field's identity.
    text = _LEVEL_FACTORS_RE.sub("", text)
    text = _LEVEL_FIELD_RE.sub("", text)
    return " ".join(_PUNCT_RE.sub(" ", text).split())


def field_for_label(label: str) -> str | None:
    """Canonical field name for an export's column header or row label."""
    normalized = _normalize_label(label)
    if not normalized:
        return None
    for canonical, aliases in FIELD_ALIASES.items():
        if normalized in aliases:
            return canonical
    return None


# --------------------------------------------------------------------------
# Tier identifiers
# --------------------------------------------------------------------------


def _split(pattern: re.Pattern[str], value: str) -> tuple[str, str]:
    match = pattern.match(value or "")
    if not match:
        return "", " ".join((value or "").split())
    return match.group(1), " ".join((match.group(2) or "").split())


def parse_reference(value: str) -> tuple[str, str]:
    """`01.a Access Control Policy` -> `("01.a", "Access Control Policy")`."""
    return _split(REFERENCE_RE, value)


def parse_objective(value: str) -> tuple[str, str]:
    """`01.01 Business Requirement...` -> `("01.01", "Business Requirement...")`."""
    return _split(OBJECTIVE_RE, value)


def parse_category(value: str) -> tuple[str, str]:
    """`01.0 - Access Control` -> `("01.0", "Access Control")`."""
    return _split(CATEGORY_RE, value)


def parse_level(value: str) -> tuple[str, str]:
    """`Level FedRAMP` -> `("Level FedRAMP", "overlay")`.

    The label is returned verbatim rather than reduced to its name, because
    it is what the export says and what an assessor will search for.
    """
    label = " ".join((value or "").split())
    match = LEVEL_RE.match(label)
    if not match:
        return label, OVERLAY
    return label, MATURITY if match.group(1).strip() in MATURITY_NAMES else OVERLAY


#: Level-scoped field labels carry their level as a prefix: "Level 2
#: Organizational Factors:", "Level FedRAMP Implementation:". The level is
#: everything between "Level" and the field name.
_LEVEL_IN_LABEL_RE = re.compile(
    r"^\s*(Level\s+.*?)\s+(?:Organizational|Organisational|System|Regulatory)\s+Factors\b"
    r"|^\s*(Level\s+.*?)\s+Implementation\b"
    r"|^\s*(Level\s+.*?)\s+Control\s+Standard\b",
    re.IGNORECASE,
)


def level_from_label(label: str) -> str:
    """The level a level-scoped field label names, or "".

    `"Level FedRAMP Implementation:"` -> `"Level FedRAMP"`. Used by the
    label/value readers, where a requirement's level is carried by the
    caption beside the value rather than by a column of its own.
    """
    text = " ".join((label or "").split())
    match = _LEVEL_IN_LABEL_RE.match(text)
    if not match:
        # A bare "Level 1" caption, which is how a rendered report opens a
        # level's block.
        return text if LEVEL_RE.match(text) else ""
    for group in match.groups():
        if group:
            return " ".join(group.split())
    return ""


def level_may_be_truncated(label: str) -> bool:
    """Whether a level label is long enough to have been clipped by SSRS."""
    return len((label or "").rstrip()) >= LEVEL_TRUNCATION - 1


def merge_level_names(labels: list[str]) -> dict[str, str]:
    """Map every level label onto the longest form seen anywhere.

    A CSV cuts the level column at 36 characters while the caption columns
    beside it, and the MHTML rendering of the same report, keep the whole
    name. Given every label an export mentions, this recovers the full one
    so `Level Digital Personal Data Protecti` and `Level Digital Personal
    Data Protection Act` do not become two levels.
    """
    cleaned = sorted({" ".join(la.split()) for la in labels if la and la.strip()}, key=len)
    resolved: dict[str, str] = {}
    for label in cleaned:
        resolved[label] = label
        for shorter in cleaned:
            if len(shorter) < len(label) and label.startswith(shorter):
                resolved[shorter] = label
    return resolved


# --------------------------------------------------------------------------
# Multi-value cells
# --------------------------------------------------------------------------


def split_lines(cell: str) -> list[str]:
    """One list entry per line of a factor or mapping cell.

    CSV exports use CRLF inside quoted cells; the MHTML rendering uses
    `<br/>`, which an HTML reader turns into a newline before it reaches
    here. Blank entries and the non-breaking spaces SSRS pads empty cells
    with are dropped.
    """
    if not cell:
        return []
    text = str(cell).replace("\r\n", "\n").replace("\r", "\n")
    out = []
    for line in text.split("\n"):
        # U+00A0 is what SSRS pads an otherwise empty cell with. Written
        # as an escape rather than literally, so the source never carries
        # a character indistinguishable from a space to the next reader.
        stripped = line.replace("\xa0", " ").strip()
        if stripped:
            out.append(stripped)
    return out


# --------------------------------------------------------------------------
# The authoritative-source crosswalk
# --------------------------------------------------------------------------

#: A prefix is treated as a complete source name once this many different
#: tokens are seen following it. Identifiers vary wildly and source names do
#: not, so the count separates them. Six is low enough to catch a source
#: cited only a handful of times, and high enough that a two-word source
#: name is not cut after its first word.
MIN_BRANCH = 6

#: Source names never run this long; the cap stops a pathological line from
#: walking the whole string.
MAX_SOURCE_TOKENS = 12

#: Trailing marks that belong to the identifier rather than the source, and
#: which HITRUST writes with a space before them ("HIPAA Security Rule
#: § 164.308").
_SOURCE_TRIM = " §¶#:,-–"  # noqa: RUF001 - the en dash occurs in the data

#: A standard's *number* is part of its name, not the start of a citation
#: into it: `27002:2022` in `ISO/IEC 27002:2022 8(2)`, `23894` in `ISO/IEC
#: 23894`. Branching alone cannot see that, because a publisher who issues
#: many standards ("ISO/IEC", "NIST SP") branches at exactly the point the
#: name is still incomplete — which split every ISO citation in a v11.7
#: library under a source called `ISO/IEC`, collapsing 27001, 27002 and
#: 27799 into one framework.
#:
#: Three leading digits at minimum, so that short section numbers stay on
#: the identifier side: `1.08` under HHS CPGs is a citation, `27001:2022`
#: is a standard.
_STANDARD_NUMBER_RE = re.compile(r"^\d{3,5}(?:[:\-.]\d{1,4})*$")


def learn_sources(lines: list[str], *, min_branch: int = MIN_BRANCH) -> set[str]:
    """Learn the authoritative-source vocabulary from the mapping lines.

    Walks each line from its first token, extending the candidate source
    while what follows is predictable, and stopping at the first prefix with
    `min_branch` distinct continuations. `NIST SP 800-53 r5` survives that
    walk because only `r5` and `r4` ever follow `NIST SP 800-53`, and the
    walk halts there because hundreds of different control ids follow `r5`.

    Learned rather than listed on purpose. A hard-coded vocabulary would
    have to be updated every CSF release, would be wrong for the community
    and de-identification supplements, and would mean shipping a piece of
    HITRUST's own content in this repository.
    """
    children: dict[str, set[str]] = defaultdict(set)
    tokenized = [line.split(" ") for line in lines if line]
    for tokens in tokenized:
        for size in range(1, min(len(tokens), MAX_SOURCE_TOKENS) + 1):
            if size < len(tokens):
                children[" ".join(tokens[:size])].add(tokens[size])

    sources: set[str] = set()
    for tokens in tokenized:
        limit = min(len(tokens), MAX_SOURCE_TOKENS)
        chosen = ""
        for size in range(1, limit + 1):
            prefix = " ".join(tokens[:size])
            # Stop where the continuation becomes unpredictable, or at the
            # last token that can still leave an identifier behind.
            if len(children[prefix]) >= min_branch or size == len(tokens) - 1:
                # ...unless what follows is the standard's own number, in
                # which case the name is not finished yet.
                if size < len(tokens) and _STANDARD_NUMBER_RE.match(tokens[size]):
                    continue
                chosen = prefix
                break
        candidate = (chosen or " ".join(tokens[:1])).strip(_SOURCE_TRIM)
        if candidate:
            sources.add(candidate)
    return sources


def split_mapping(line: str, sources: set[str]) -> tuple[str, str]:
    """Split one mapping line into `(source, identifier)`.

    Longest match wins, so `NIST SP 800-53 r5` beats `NIST`. A line no
    learned source matches is returned whole as the identifier under an
    empty source rather than guessed at -- a mapping filed under the wrong
    framework is worse than one filed under none.
    """
    text = " ".join((line or "").split())
    best = ""
    for source in sources:
        if len(source) <= len(best) or not text.startswith(source):
            continue
        # A source only matches on a token boundary, so `NIST SP 800-53 r5`
        # never matches a line that merely begins `NIST SP 800-53 r53`.
        if len(text) == len(source) or not text[len(source)].isalnum():
            best = source
    if not best:
        return "", text
    return best, text[len(best) :].strip(_SOURCE_TRIM).strip()


def build_mappings(cell: str, sources: set[str]) -> dict[str, list[str]]:
    """`{source: [identifier, ...]}` for one requirement's mapping cell."""
    grouped: dict[str, list[str]] = defaultdict(list)
    for line in split_lines(cell):
        source, identifier = split_mapping(line, sources)
        if identifier and identifier not in grouped[source]:
            grouped[source].append(identifier)
    return dict(grouped)


# --------------------------------------------------------------------------
# Records -> Controls
# --------------------------------------------------------------------------


@dataclass
class Record:
    """One (control reference x level) row, with its fields already named.

    The intermediate every format lands on. A CSV loader, an HTML loader and
    an LLM-generated loader for some export nobody has seen yet all produce
    these, and `build_controls` is the only place that knows how a Control
    is assembled out of them.
    """

    category: str = ""
    objective: str = ""
    objective_statement: str = ""
    reference: str = ""
    specification: str = ""
    factor_type: str = ""
    level: str = ""
    statement: str = ""
    organizational_factors: str = ""
    system_factors: str = ""
    regulatory_factors: str = ""
    mapping: str = ""

    def key(self) -> tuple[str, str]:
        return (" ".join(self.reference.split()), " ".join(self.level.split()))


def dedupe(records: list[Record]) -> list[Record]:
    """Collapse the report's repeated rows, keeping one per reference+level.

    A MyCSF CSV repeats whole rows -- 2,818 for 1,219 real records in v11.7
    -- because the report joins against tables it does not render. The
    duplicates are byte-identical, so keeping one loses nothing. Where two
    rows share a key but differ, the longer statement wins, on the grounds
    that the shorter one is the truncated render.
    """
    kept: dict[tuple[str, str], Record] = {}
    for record in records:
        if not record.reference or not record.level:
            continue
        existing = kept.get(record.key())
        if existing is None or len(record.statement) > len(existing.statement):
            kept[record.key()] = record
    return list(kept.values())


def build_controls(
    records: list[Record],
    *,
    version: str = "",
    source_path: str | None = None,
) -> list[Control]:
    """Assemble deduplicated records into one `Control` per control reference.

    Requirements are ordered maturity-first and then by label, so Level
    1/2/3 read as the ladder they are and the overlays follow in a stable
    order rather than in whatever order the report emitted them.
    """
    records = dedupe(records)
    sources = learn_sources([line for r in records for line in split_lines(r.mapping)])
    full_level = merge_level_names([r.level for r in records])

    grouped: dict[str, list[Record]] = defaultdict(list)
    order: list[str] = []
    for record in records:
        reference_id, _ = parse_reference(record.reference)
        key = reference_id or " ".join(record.reference.split())
        if key not in grouped:
            order.append(key)
        grouped[key].append(record)

    controls: list[Control] = []
    for key in order:
        rows = grouped[key]
        head = rows[0]
        reference_id, reference_title = parse_reference(head.reference)
        category_id, category_title = parse_category(head.category)
        objective_id, objective_title = parse_objective(head.objective)

        requirements = []
        for row in rows:
            label = full_level.get(" ".join(row.level.split()), row.level)
            label, kind = parse_level(label)
            requirements.append(
                Requirement(
                    requirement_id=f"{reference_id or key} {label}".strip(),
                    level=label,
                    level_kind=kind,
                    statement=" ".join(row.statement.split()),
                    organizational_factors=split_lines(row.organizational_factors),
                    system_factors=split_lines(row.system_factors),
                    regulatory_factors=split_lines(row.regulatory_factors),
                    mappings=build_mappings(row.mapping, sources),
                )
            )
        requirements.sort(key=_requirement_order)

        controls.append(
            Control(
                control_id=reference_id or key,
                title=reference_title,
                framework=FRAMEWORK,
                framework_version=version,
                family=category_title or None,
                family_abbr=category_id or None,
                objective_id=objective_id,
                objective_title=objective_title,
                objective_statement=" ".join(head.objective_statement.split()),
                factor_type=" ".join(head.factor_type.split()),
                control_statement=" ".join(head.specification.split()),
                # The levels this control is stated at. The closest thing
                # HITRUST has to 800-53's low/moderate/high, and what the
                # pipeline's baseline filters read.
                baseline=", ".join(r.level for r in requirements) or None,
                requirements=requirements,
                source_path=source_path,
            )
        )
    return controls


def _requirement_order(requirement: Requirement) -> tuple[int, str]:
    if requirement.level_kind == MATURITY:
        return (0, requirement.level)
    return (1, requirement.level)


# --------------------------------------------------------------------------
# Reporting
# --------------------------------------------------------------------------


@dataclass
class Summary:
    """What a parse produced, and whether it looks like a whole library."""

    categories: int = 0
    objectives: int = 0
    references: int = 0
    requirements: int = 0
    maturity_levels: int = 0
    overlay_levels: int = 0
    sources: int = 0
    mapped_identifiers: int = 0
    levels: Counter = field(default_factory=Counter)
    top_sources: list[tuple[str, int]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def format_report(self) -> str:
        lines = [
            f"HITRUST CSF: {self.references} control references, "
            f"{self.requirements} requirement statements",
            f"  {self.categories} categories, {self.objectives} objectives",
            f"  {self.maturity_levels} maturity levels, {self.overlay_levels} overlays",
            f"  {self.mapped_identifiers} mapped identifiers across {self.sources} sources",
        ]
        if self.top_sources:
            lines.append("")
            lines.append("  most-mapped authoritative sources:")
            width = min(max(len(s) for s, _ in self.top_sources), 46)
            for source, count in self.top_sources:
                lines.append(f"    {source[:46].ljust(width)}  {count}")
        if self.warnings:
            lines.append("")
            for warning in self.warnings:
                lines.append(f"  warn  {warning}")
        return "\n".join(lines)


def summarize(controls: list[Control], *, top: int = 12) -> Summary:
    """Describe a parsed catalog, and say when it looks incomplete.

    Worth running after every parse. The failure mode of a heuristic loader
    is not an exception but a plausible-looking catalog with a third of the
    library missing, and only the counts show that.
    """
    summary = Summary()
    summary.references = len(controls)
    summary.categories = len({c.family_abbr for c in controls if c.family_abbr})
    summary.objectives = len({c.objective_id for c in controls if c.objective_id})

    source_counts: Counter = Counter()
    kinds: Counter = Counter()
    for control in controls:
        for requirement in control.requirements:
            summary.requirements += 1
            summary.levels[requirement.level] += 1
            kinds[requirement.level_kind] += 1
            for source, identifiers in requirement.mappings.items():
                summary.mapped_identifiers += len(identifiers)
                source_counts[source or "(unrecognised)"] += len(identifiers)

    summary.maturity_levels = len(
        {r.level for c in controls for r in c.requirements if r.level_kind == MATURITY}
    )
    summary.overlay_levels = len(
        {r.level for c in controls for r in c.requirements if r.level_kind == OVERLAY}
    )
    summary.sources = len(source_counts)
    summary.top_sources = source_counts.most_common(top)

    for tier, expected in EXPECTED.items():
        actual = getattr(summary, tier)
        if actual and actual < expected * 0.6:
            summary.warnings.append(
                f"{actual} {tier} parsed, against {expected} in a full v11.7 "
                "library -- this looks like a partial export or a missed column."
            )
    if summary.requirements and not summary.mapped_identifiers:
        summary.warnings.append(
            "no authoritative-source mappings parsed, so no crosswalk can be "
            "built from this export -- check that the mapping column was found."
        )
    if kinds and not kinds.get(MATURITY):
        summary.warnings.append(
            "no Level 1/2/3 requirements found, which every control reference "
            "should have -- the level column may have been misidentified."
        )
    return summary
