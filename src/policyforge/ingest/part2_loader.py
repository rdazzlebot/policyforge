"""42 CFR Part 2 — confidentiality of substance use disorder patient records.

**What this module does today is read the part into sections. It does not
build a catalog, and the reason is a product question that is still open**
— see "The shape question" below. Everything here is the half that is true
whichever way that question is answered, so the parts that depend on it are
absent rather than guessed at.

**Part 2 is mostly conduct, not controls**, and that is the same trap 45 CFR
171 set. 800-53 says what to implement. Most of Part 2 says when a
disclosure is permitted, what a consent must contain, and what a court must
find before it orders a record produced. Citing § 2.66 asserts that a court
*may* authorise a disclosure; it does not assert that a control exists. A
catalog that crosswalked these to 800-53 by resemblance would be wrong in
the direction that is hardest to see, because every entry would look
plausible.

**One section is genuinely about security, and it was verified against the
fetched text rather than remembered.** § 2.16, "Security for records and
notification of breaches", requires formal policies and procedures covering
transfer and removal of paper records, destruction including sanitizing
hard-copy media to non-retrievable, secure rooms and locked containers,
workstation access, and de-identification to 45 CFR 164.514(b) — then the
same list for electronic records — and imports 45 CFR part 160 and subpart
D of part 164 for breach notification.

**§ 2.16 is a hub rather than an island**, which is the finding that makes
the shape a product call. Three other sections impose security obligations
by pointing back at it rather than by stating their own:

    2.19(a)  sanitize media "in a manner consistent with the policies and
             procedures established under § 2.16"
    2.52(b)  "Must maintain and destroy patient identifying information in
             accordance with the security policies and procedures
             established under § 2.16."
    2.53     auditors and researchers agree in writing to the same regime

§ 2.19 is the one to notice. "Disposition of records by discontinued
programs" reads administrative, and its body is retention periods, labelled
sealed containers, sanitizing printer ribbons and drums, and a one-year
deadline for wiping electronic media. **A control section wearing a conduct
heading**, which is why the sections here were classified by reading them
rather than by their headings.

THE SHAPE QUESTION, unresolved and deliberately not pre-empted: whether the
catalog is § 2.16 alone, or § 2.16 with the cross-referencing obligations
carried as its requirements rather than as controls of their own. The text
supports the second — § 2.19's duty is not independent, it is § 2.16
applied to a program shutting down, so modelling it separately would
crosswalk one requirement twice. Whichever lands, a Part 2 catalog is about
one control with a handful of requirements rather than thirty-eight
entries, and **that thinness is the correct answer rather than a parse
failure.** An emitter written before the ruling would have had to assume
one, and the assumption would have been invisible in the output.

**Fetching is `ingest/ecfr.py`**, shared with every regulation this project
reads, and it already covers this part: `tests/test_ecfr_fetch.py` pins
`(42, "2", "title-42.xml?part=2")`. The wrappers below name Part 2's own
coordinates, because "which title and part is the confidentiality rule" is
a property of the regulation rather than a choice an ETL command makes.
"""

from __future__ import annotations

import re

# The XXE and entity-expansion analysis for this parser is in
# `info_blocking.py`, measured against CPython rather than argued from the
# rule text, and it applies here unchanged because this module parses the
# same source through the same parser.
#
# Restating only the condition that ends it, because a module that inherited
# the conclusion without the premise would keep the conclusion after the
# premise stopped holding: it rests on `ecfr._API` being a fixed constant, so
# the XML cannot come from a host an attacker chooses. If the fetch ever
# takes an operator-supplied URL, or this parser is pointed at third-party
# XML, `defusedxml` becomes the right answer here and there.
#
# nosemgrep: python.lang.security.use-defused-xml.use-defused-xml
import xml.etree.ElementTree as ET  # nosec B405
from dataclasses import dataclass

#: Part 2's own coordinates.
TITLE = 42
PART = "2"

FRAMEWORK = "42 CFR Part 2"
FRAMEWORK_VERSION = "42 CFR Part 2"

#: A section identifier as *this part* numbers them, derived from the part
#: rather than adapted from a neighbour. Part 2 runs `2.1` to `2.68`: one or
#: two digits after the dot, never three.
#:
#: Stated as a measurement because the near miss is silent. Part 171's
#: pattern is `^171\.\d{3,4}$`, and against Part 2's 38 real section numbers
#: it matches **zero** — so a catalog built on a copied pattern comes out
#: empty, with nothing raising and every downstream check passing on the
#: nothing. `_require_sections` exists so that failure is loud.
SECTION_ID_RE = re.compile(r"^2\.\d{1,2}$")

#: How many sections Part 2 had when this parser was written, at the
#: 2026-09-17 revision. **A pinned observation, not an invariant** — the CFR
#: gains and loses sections, and the day this number is wrong is a day
#: someone should look at the part rather than a day the parser is broken.
#: `_require_sections` says which of the two it is looking at.
EXPECTED_SECTIONS = 38

#: Sections that carry a number and a title and no obligation. Dropped for
#: the reason `hipaa_loader` drops them — a defined term is not a
#: requirement — and *asserted absent* rather than listed as exceptions,
#: because an exception list has to be kept in step with the source while an
#: assertion of absence cannot drift.
_NON_OBLIGATION_RE = re.compile(
    r"\[reserved\]|^definitions|^statutory authority|^purpose and effect",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Section:
    """One numbered section of the part, as published."""

    number: str
    title: str
    text: str

    @property
    def states_an_obligation(self) -> bool:
        """Whether this section carries duties, as opposed to vocabulary.

        A title-level test, and deliberately only that. Whether a section
        that *does* carry duties carries a **control** is the open shape
        question, and it is not answerable from the heading — § 2.19's
        heading says "Disposition of records by discontinued programs" and
        its body is media sanitization. Nothing here should be read as
        deciding it.
        """
        return not _NON_OBLIGATION_RE.search(self.title)


def _text(node: ET.Element) -> str:
    """All text under `node`, whitespace collapsed.

    `itertext` rather than `.text`, because eCFR marks defined terms and
    paragraph names in `<I>` runs inside the paragraph, and those runs are
    content. Reading `.text` alone silently truncates at the first one.
    """
    return " ".join(" ".join(node.itertext()).split())


def _section_title(head: str, number: str) -> str:
    """The heading with its section symbol and number stripped.

    eCFR writes the whole heading into one node: "§ 2.16 Security for
    records and notification of breaches." The number is already the id.
    """
    stripped = re.sub(rf"^\s*§*\s*{re.escape(number)}\s*", "", head.lstrip("§ "))
    return stripped.strip()


def _require_sections(found: list[Section]) -> None:
    """Refuse a parse that found too little, and say which failure it is.

    The failure this guards against does not raise on its own. A pattern
    that matches nothing yields an empty catalog, and an empty catalog
    passes every check that asks whether its entries are well-formed. So
    the count is checked against a number someone wrote down, and the two
    ways it can be wrong are reported differently, because they need
    different responses from whoever reads the message.
    """
    if not found:
        raise ValueError(
            f"Parsed 0 sections from 42 CFR Part {PART}. Expected about "
            f"{EXPECTED_SECTIONS}. This is a parser fault rather than a change "
            f"in the regulation: check SECTION_ID_RE ({SECTION_ID_RE.pattern!r}) "
            f"against the section numbers the XML actually carries."
        )
    if len(found) != EXPECTED_SECTIONS:
        raise ValueError(
            f"Parsed {len(found)} sections from 42 CFR Part {PART}, expected "
            f"{EXPECTED_SECTIONS} as of the 2026-09-17 revision. The part may "
            f"have changed, which is information rather than a bug: read the "
            f"diff, then update EXPECTED_SECTIONS in the same commit that "
            f"accounts for it. Found: {', '.join(s.number for s in found)}"
        )


def sections(xml: str, *, strict: bool = True) -> list[Section]:
    """Every numbered section of the part, in the order published.

    `strict` off parses an excerpt — a test fixture holds six sections by
    design — and is not a way to skip the count check on a real document.
    """
    root = ET.fromstring(xml)  # nosec B314

    found: list[Section] = []
    for div in root.findall(".//DIV8"):
        number = (div.get("N") or "").strip()
        if not SECTION_ID_RE.match(number):
            continue
        head = div.find("HEAD")
        found.append(
            Section(
                number=number,
                title=_section_title(_text(head) if head is not None else "", number),
                text=_text(div),
            )
        )

    if strict:
        _require_sections(found)
    return found
