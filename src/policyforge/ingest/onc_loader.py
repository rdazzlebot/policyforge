"""Parse the ONC certification criteria (45 CFR 170.315) into control data.

Public domain, a US federal regulation, same basis as the HIPAA Security
Rule — so it is safe to bundle. Fetched through `ingest/ecfr.py`, the shared
eCFR client, with this part's coordinates named here rather than threaded
through every call.

**The structure is not in the XML.** 164 Subpart C nests its paragraphs as
elements, and `hipaa_loader` walks that tree. 170.315 is a *single* section
with 540 flat `<P>` children whose hierarchy lives in the text:

    (a) Clinical—(1) Computerized provider order entry—medications. (i) Enable…
    (b) Care coordination—(1) Transitions of care—(i) Send and receive via…

So the parse reconstructs the tree from labels at the start of paragraphs
and from em-dash runs inside them.

**The trap, and the reason this module exists rather than a regex in the
ETL command:** `^\\([a-z]\\)` cannot tell the criterion `(i)` from a
sub-paragraph `(i)`. Forty-seven paragraphs in this section open with
`(i)` and exactly one of them is a criterion. Reading them all as criteria
invents `170.315(v)` and `170.315(x)`, which do not exist — and nothing
crashes: the catalog loads, the controls look plausible, and every document
generated from it inherits ids an assessor cannot follow.

What distinguishes them is **ordinal position, not spelling**. The section
opens at `(a)`, so the only label that can begin a new criterion is the
successor of the last one seen. A `(i)` following `(h)` is criterion (i); a
`(i)` anywhere else opens or continues a sub-list.

`170.315(i)` is `[Reserved]` and **must not be emitted**. A reserved
criterion emitted as a control would be permanently unsatisfiable — it
counts, it renders, it crosswalks, and it means nothing — and every coverage
report after it would carry a gap that can never close.

`tests/test_onc_loader.py` asserts today that the source's letter run is
unbroken and that `(i)` is the reserved one. **The other half of the pairing
is owed by whoever builds the emitter**: the catalog must be asserted not to
contain `170.315(i)`, so the omission is asserted rather than silent. Both
halves together are what prove the parser saw ten criteria and emitted nine
deliberately; only the first half exists here, because there is no emitter
yet. That pairing is policyforge-80's, following
`test_reserved_sections_are_absent` in the information-blocking loader.
"""

from __future__ import annotations

import re

# Bandit (B405/B314) and semgrep both want `defusedxml` here. The reasoning
# for not taking it is measured rather than argued, and it lives once in
# `info_blocking.py` — XXE refused, no external DTD fetched, internal entity
# expansion accepted deliberately because the input is one document fetched
# over HTTPS from the fixed `ecfr._API` host by a command the operator runs.
# Pointed at rather than repeated: two copies of an analysis drift, and the
# copy that drifts is the one nobody re-measured.
#
# **The premise is the same and so is its expiry:** if this parser is ever
# pointed at operator-supplied or third-party XML, that reasoning stops
# holding here exactly as it stops holding there.
#
# nosemgrep: python.lang.security.use-defused-xml.use-defused-xml
import xml.etree.ElementTree as ET  # nosec B405

from policyforge.ingest import ecfr
from policyforge.ingest.schema import Control

#: Where this part lives, named once. `ecfr.py` takes them as arguments so
#: one client serves every CFR part; a reader of this module should not have
#: to open that one to learn which regulation it fetches.
TITLE = 45
PART = "170"

#: The section carrying the certification criteria. The rest of part 170 is
#: definitions, applicability and the certification program's own rules.
CRITERIA_SECTION = "170.315"

#: A parenthesised label at the very start of a paragraph: `(a)`, `(1)`,
#: `(iv)`, `(A)`. Deliberately broad — deciding what a label *means* is the
#: sequential rule's job, not this pattern's.
_LABEL = re.compile(r"^\(([a-z]+|\d+|[A-Z])\)\s*")

#: Paragraphs the regulation marks as holding nothing.
_RESERVED = re.compile(r"\[Reserved\]", re.IGNORECASE)


def current_ecfr_date() -> str:
    """eCFR's current published date for Title 45."""
    return ecfr.current_date(TITLE)


def ecfr_source_url(date: str) -> str:
    """The URL this part was fetched from, for the provenance stamp."""
    return ecfr.source_url(date, title=TITLE, part=PART)


def fetch_part_xml(*, date: str | None = None) -> str:
    """The XML of 45 CFR 170 as eCFR served it on `date`."""
    return ecfr.fetch_part_xml(title=TITLE, part=PART, date=date)


def criteria_paragraphs(xml_text: str) -> list[str]:
    """Every paragraph of § 170.315, flat, in document order."""
    root = ET.fromstring(xml_text)  # nosec B314 - see the import
    for division in root.iter("DIV8"):
        if (division.get("N") or "").startswith(CRITERIA_SECTION):
            return ["".join(p.itertext()).strip() for p in division.findall("P")]
    return []


def criterion_letters(paragraphs: list[str]) -> list[tuple[str, str]]:
    """The top-level criteria, as `(letter, paragraph)` in order.

    A criterion's label is the successor of the last one seen — the rule
    that separates criterion `(i)` from the forty-seven sub-paragraph
    `(i)`s. Returns what the *source* contains, including any reserved
    criterion, so a caller can assert the run is unbroken before deciding
    what to emit.
    """
    found: list[tuple[str, str]] = []
    expected = "a"
    for text in paragraphs:
        match = _LABEL.match(text)
        if match and match.group(1) == expected:
            found.append((expected, text))
            expected = chr(ord(expected) + 1)
    return found


def is_reserved(paragraph: str) -> bool:
    """Does this paragraph say the regulation has put nothing here?

    **A reserved criterion is found and then not emitted.** `170.315(i)` is
    `[Reserved]`, and a control emitted for it would be permanently
    unsatisfiable: it counts, it renders, it crosswalks, and it means
    nothing — so every coverage report afterwards carries a gap that can
    never close, in output an assessor reads. `info_blocking` drops
    `171.402` for the same reason.

    The objection to dropping it is that a silent omission is
    indistinguishable from a parse failure, which is a real hazard and the
    reason for a pairing of two assertions. The first exists:
    `tests/test_onc_loader.py` asserts the letter run **in the source** is
    unbroken from `(a)` to `(j)`. **The second is owed and does not exist
    yet** — the emitted catalog must be asserted not to contain
    `170.315(i)`, and there is no emitter to assert it against. Together
    they would prove the parser saw ten and emitted nine deliberately; alone,
    the first proves only that it saw ten.

    Which is also why "no emitted control has an empty statement" carries
    **no exception** for reserved paragraphs. An exception has to be kept in
    step with the source and can drift as the regulation changes; a rule
    with no exception cannot. That pairing is policyforge-80's ruling of
    2026-09-18, kept here rather than only in the pull request because a PR
    body is not read by whoever edits this file in six months.
    """
    return bool(_RESERVED.search(paragraph))


#: The declared name, which has to be a legal source tag. `45 CFR 170`
#: begins with a digit and `content/tags.SOURCE_TAG_RE` builds a framework
#: name out of capital-initial words, so a catalog declaring it could not
#: be cited by any document -- the defect that shipped in two other CFR
#: catalogs and was fixed by renaming them. Taken from the section's own
#: heading, "ONC certification criteria for Health IT", so the name a
#: person types is the name the regulation uses.
FRAMEWORK = "ONC Certification Criteria"
FRAMEWORK_VERSION = "45 CFR 170.315"

#: `(a) Clinical—` or `(j) Modular API capabilities.` A category names
#: itself, then either an em dash with its first criterion inline or a
#: period with prose following. Both spellings occur; matching only the
#: em dash loses category (j) entirely.
_CATEGORY_NAME = re.compile(r"^\([a-z]\)\s*(?P<name>[^—.(]+?)\s*(?P<sep>[—.])")

#: `(4) Drug-drug ...` or the reserved range `(1)-(19) [Reserved]`.
_CRITERION_NUMBER = re.compile(r"^\((?P<first>\d+)\)(?:\s*[-\u2013\u2014]\s*\((?P<last>\d+)\))?")


def _category_name(paragraph: str) -> str:
    """The category's own name, without its letter or its first criterion."""
    match = _CATEGORY_NAME.match(paragraph)
    return match.group("name").strip() if match else ""


def _after_category_label(paragraph: str) -> str:
    """What follows `(a) Clinical—`, which is that category's first criterion.

    Empty when the category is introduced with a period instead, because
    then the paragraph is prose and the criteria start in the next one.
    """
    match = _CATEGORY_NAME.match(paragraph)
    if not match or match.group("sep") != "\u2014":
        return ""
    return paragraph[match.end() :]


def _criterion_title(body: str) -> str:
    """The criterion's name, which runs to the end of its first sentence.

    Splitting on the em dash instead would cut "Computerized provider
    order entry—medications" down to the half it shares with (a)(2) and
    (a)(3), giving three criteria one title.
    """
    first = re.split(r"\.\s", body, maxsplit=1)[0].strip().rstrip(".")
    # A criterion whose first sentence already runs into its sub-list --
    # "Drug-drug ... for CPOE—(i) Interventions" -- keeps only the part
    # before the sub-label.
    return re.split(r"\s*\((?:i|a|1)\)\s", first, maxsplit=1)[0].strip().rstrip("—-")


def parse_onc_criteria(xml_text: str) -> tuple[list[Control], list[str]]:
    """The certification criteria of § 170.315, and the reserved ids skipped.

    Returns `(controls, reserved)` rather than logging the second, so the
    caller reports what was deliberately left out instead of the omission
    being invisible -- the same contract `parse_oscal_catalog` uses for
    withdrawn controls.

    **One criterion is a control.** `170.315(g)(10)` is how these are
    cited, by developers and in ONC's own programme documents, so that is
    the id. The lettered category above it -- `(g) Design and performance`
    -- is the family, and the sub-paragraphs below it stay in the
    statement: they are the conditions of one capability rather than
    separate duties, which is the split `info_blocking` makes for a
    condition of an exception.

    **The number level repeats the letter level's trap.** 182 paragraphs
    open with `(N)` and most are sub-lists: `(1) To a specific set of
    identified users.` sits three levels inside `(a)(4)`. So a criterion
    number must be the successor of the last one *in its own category*,
    the same ordinal rule `criterion_letters` applies to letters. Without
    it the catalog gains dozens of controls whose ids resolve to sub-
    clauses, and nothing crashes.
    """
    paragraphs = criteria_paragraphs(xml_text)
    anchors = criterion_letters(paragraphs)
    if not anchors:
        raise ValueError(
            f"No criterion letters found in {CRITERIA_SECTION}. The section has "
            f"{len(paragraphs)} paragraph(s); a parse that finds no criteria at all "
            f"is a parser fault rather than a change in the regulation."
        )

    positions = {id(paragraph): index for index, paragraph in enumerate(paragraphs)}
    starts = [positions[id(text)] for _letter, text in anchors]
    bounds = list(zip(starts, [*starts[1:], len(paragraphs)], strict=True))

    controls: list[Control] = []
    reserved: list[str] = []

    for (letter, anchor), (start, stop) in zip(anchors, bounds, strict=True):
        family = _category_name(anchor)
        number = 0
        # The category paragraph carries its own first criterion when it is
        # introduced with an em dash, so it is read before the ones after it.
        slice_ = [_after_category_label(anchor), *paragraphs[start + 1 : stop]]

        for body in slice_:
            match = _CRITERION_NUMBER.match(body)
            if not match:
                continue
            first = int(match.group("first"))
            last = int(match.group("last") or first)
            if first != number + 1:
                continue  # a sub-list, not this category's next criterion
            rest = body[match.end() :].strip()
            citation = f"{CRITERIA_SECTION}({letter})({first})"
            if is_reserved(rest):
                reserved.extend(
                    f"{CRITERIA_SECTION}({letter})({n})" for n in range(first, last + 1)
                )
            else:
                controls.append(
                    Control(
                        control_id=citation,
                        title=_criterion_title(rest),
                        framework=FRAMEWORK,
                        framework_version=FRAMEWORK_VERSION,
                        family=family,
                        family_abbr=f"({letter})",
                        control_statement=rest,
                        source_path=(
                            f"https://www.ecfr.gov/current/title-45/section-{CRITERIA_SECTION}"
                        ),
                    )
                )
            number = last

        if number == 0 and is_reserved(anchor):
            reserved.append(f"{CRITERIA_SECTION}({letter})")

    return controls, reserved
