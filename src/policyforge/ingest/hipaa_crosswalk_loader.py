"""Parse NIST's official HIPAA-Security-Rule-to-SP-800-53-Rev-5 crosswalk and
attach it to the HIPAA controls produced by `ingest/hipaa_loader.py`.

Why this isn't parsed out of SP 800-66r2's PDF: it isn't in there. SP 800-66
Rev. 2's Appendix D describes the crosswalk but states that "the mapping
table has been removed from the document and placed online in the NIST
Cybersecurity and Privacy Reference Tool (CPRT)" — the published PDF
contains no SP 800-53 control identifiers at all. CPRT is therefore the
authoritative source, and like `hipaa_loader.py`'s use of eCFR it is fetched
from a public API rather than hand-transcribed, so the mapping can always be
regenerated and diffed against what NIST currently publishes.

Source shape (CPRT's OLIR format). The catalog is a flat list of
"OLIR entries", each of which pairs one Focal Document Element with one
Reference Document Element:

    FDE-AT-15  title "AT-03"                (the SP 800-53 Rev 5 control)
    RDE-AT-15  title "164.308(a)(5)"        (the HIPAA Security Rule citation)
    OE-AT-15                                (the entry joining the two)

The three element types are fetched separately and joined on the identifier
suffix that follows their `FDE-`/`RDE-`/`OE-` prefix. That join is exact —
the three key sets are identical, one row per pair — and is asserted at
parse time rather than assumed, because a silent join failure here would
produce confident-looking but wrong compliance mappings.

Two shape mismatches have to be reconciled against `hipaa_loader.py`'s
eCFR-derived citations, both handled by `CITATION_ALIASES` below and both
verified by comparing the two sources' requirement *text*, not by pattern-
matching citation numbers (see tests/test_hipaa_crosswalk_loader.py):

1. CPRT cites a Standard by its umbrella paragraph (e.g. "164.308(a)(5)")
   where the CFR codifies the standard itself one level deeper, at
   § 164.308(a)(5)(i). Same requirement, shorter citation.
2. A handful of citations reflect a different paragraph numbering than the
   current CFR text — most visibly "164.308(b)(4)", whose CPRT text is
   verbatim the requirement the current CFR codifies at § 164.308(b)(3) —
   and CPRT splits § 164.314(b)(2)'s group-health-plan specification into
   four sub-items (i)-(iv) that the CFR (and so this project's data) carries
   as one.

Anything that cannot be resolved this way is reported as unmatched and left
unmapped rather than guessed at; see `CrosswalkReport`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .schema import Control

# The CPRT catalog this crosswalk comes from. Pinned by identifier so a
# re-fetch is reproducible and a NIST-side version bump is visible as a
# deliberate change here rather than a silent data drift.
CPRT_FRAMEWORK_VERSION = "HIPAA-Sec-Rule-800-53-5.1.1"
CPRT_FRAMEWORK_NAME = "HIPAA-Security-Rule-to-SP-800-53-Rev-5.1.1"
CPRT_ELEMENTS_URL = (
    "https://csrc.nist.gov/extensions/nudp/services/json/nudp"
    "/framework/version/{version}/type/{element_type}/elements"
)
# Focal Document Elements are the SP 800-53 controls, Reference Document
# Elements the HIPAA citations, and OLIR entries the pairing between them.
CPRT_ELEMENT_TYPES = ("olir_entry", "fde", "rde")

# CPRT citation -> the citation `ingest/hipaa_loader.py` derives from eCFR.
# Every entry is asserted text-equivalent against the eCFR data in
# tests/test_hipaa_crosswalk_loader.py, so a future CFR renumbering or CPRT
# revision fails the suite instead of silently mis-mapping a requirement.
CITATION_ALIASES = {
    # (1) Standard cited at its umbrella paragraph; the CFR codifies the
    #     standard itself one level deeper.
    "164.308(a)(1)": "164.308(a)(1)(i)",
    "164.308(a)(3)": "164.308(a)(3)(i)",
    "164.308(a)(4)": "164.308(a)(4)(i)",
    "164.308(a)(5)": "164.308(a)(5)(i)",
    "164.308(a)(6)": "164.308(a)(6)(i)",
    "164.308(a)(7)": "164.308(a)(7)(i)",
    "164.310(a)": "164.310(a)(1)",
    "164.310(d)": "164.310(d)(1)",
    "164.312(a)": "164.312(a)(1)",
    "164.312(c)": "164.312(c)(1)",
    "164.314(a)": "164.314(a)(1)",
    "164.314(b)": "164.314(b)(1)",
    "164.316(b)": "164.316(b)(1)",
    # (2a) Different paragraph numbering: CPRT's "164.308(b)(4)" carries
    #      verbatim the text the current CFR codifies at § 164.308(b)(3)
    #      ("Written contract or other arrangement").
    "164.308(b)(4)": "164.308(b)(3)",
    # (2b) CPRT splits § 164.314(b)(2)'s single Required implementation
    #      specification into its four sub-items; the CFR presents them as
    #      one paragraph, so all four fold onto that one requirement and
    #      their SP 800-53 controls are unioned.
    "164.314(b)(2)(i)": "164.314(b)(2)",
    "164.314(b)(2)(ii)": "164.314(b)(2)",
    "164.314(b)(2)(iii)": "164.314(b)(2)",
    "164.314(b)(2)(iv)": "164.314(b)(2)",
}

# CPRT writes SP 800-53 IDs zero-padded ("AC-01", "CP-02(08)"); the rest of
# this project uses the unpadded form NIST itself prints in SP 800-53
# ("AC-1", "CP-2(8)"), which is also what mapping/crosswalk.py's ID regex
# and the NIST vault loader produce.
_NIST_ID_RE = re.compile(r"^([A-Za-z]{2})-0*(\d+)(?:\s*\(0*(\d+)\))?$")
_HIPAA_CITATION_RE = re.compile(r"^164\.\d{3}(?:\([A-Za-z0-9]+\))*$")


@dataclass
class CrosswalkReport:
    """What `apply_crosswalk` actually managed to attach, and what it didn't.

    Deliberately surfaces the negative cases: this is compliance data, so a
    citation that couldn't be resolved needs to be visible rather than
    quietly absent.
    """

    mapped_controls: int = 0
    mapped_enhancements: int = 0
    #: CPRT citations with no counterpart in the eCFR-derived HIPAA data.
    unmatched_citations: list[str] = field(default_factory=list)
    #: CPRT SP 800-53 IDs that didn't parse into a normalized control ID.
    unparsed_nist_ids: list[str] = field(default_factory=list)
    #: HIPAA requirements NIST's crosswalk simply doesn't cover.
    unmapped_requirements: list[str] = field(default_factory=list)


def _normalize_nist_id(raw: str) -> str | None:
    """Normalize a CPRT control ID: "AC-01" -> "AC-1", "CP-02(08)" -> "CP-2(8)".

    Returns None for anything that isn't recognizably an SP 800-53 control
    ID, so the caller can report it instead of writing a guess into the data.
    """
    match = _NIST_ID_RE.match(raw.strip())
    if match is None:
        return None
    family, number, enhancement = match.groups()
    control_id = f"{family.upper()}-{int(number)}"
    return f"{control_id}({int(enhancement)})" if enhancement else control_id


def _sort_key(nist_id: str) -> tuple[str, int, int]:
    """Sort SP 800-53 IDs the way NIST prints them — AC-2 before AC-11,
    AC-2 before AC-2(1) — rather than lexically."""
    match = _NIST_ID_RE.match(nist_id)
    if match is None:  # pragma: no cover - normalized IDs always match
        return (nist_id, 0, 0)
    family, number, enhancement = match.groups()
    return (family, int(number), int(enhancement) if enhancement else 0)


def _elements(payload: dict, element_type: str) -> list[dict]:
    try:
        return payload[element_type]["response"]["elements"]
    except (KeyError, TypeError) as exc:
        raise ValueError(
            f"CPRT payload is missing a well-formed {element_type!r} element list — "
            "check the fetch against CPRT_ELEMENTS_URL."
        ) from exc


def parse_cprt_crosswalk(payload: dict) -> dict[str, list[str]]:
    """Join CPRT's OLIR element lists into `{hipaa_citation: [nist_id, ...]}`.

    `payload` maps each name in `CPRT_ELEMENT_TYPES` to that element type's
    raw CPRT API response (what `fetch_cprt_crosswalk` returns).
    """
    keyed: dict[str, dict[str, dict]] = {}
    for element_type, prefix in (("fde", "FDE-"), ("rde", "RDE-"), ("olir_entry", "OE-")):
        by_key: dict[str, dict] = {}
        for element in _elements(payload, element_type):
            identifier = element["elementIdentifier"]
            if not identifier.startswith(prefix):
                raise ValueError(
                    f"CPRT {element_type} identifier {identifier!r} does not start with "
                    f"{prefix!r} — the OLIR element naming this join relies on has changed."
                )
            by_key[identifier[len(prefix) :]] = element
        keyed[element_type] = by_key

    fde, rde, entries = keyed["fde"], keyed["rde"], keyed["olir_entry"]
    if not (set(fde) == set(rde) == set(entries)):
        raise ValueError(
            "CPRT focal/reference/entry element sets do not line up "
            f"({len(fde)} FDE, {len(rde)} RDE, {len(entries)} OLIR entries) — refusing to "
            "guess at the pairing, since a bad join would produce wrong mappings."
        )

    mapping: dict[str, list[str]] = {}
    for key in sorted(fde):
        citation = rde[key]["title"].strip()
        if not _HIPAA_CITATION_RE.match(citation):
            # Guards against the focal/reference roles being swapped upstream,
            # which would otherwise map every NIST control ID to a HIPAA
            # citation and silently invert the whole crosswalk.
            raise ValueError(
                f"CPRT reference element {key!r} has title {citation!r}, which is not a "
                "45 CFR 164 citation — check that the focal (SP 800-53) and reference "
                "(HIPAA) documents are still the way round this parser expects."
            )
        nist_id = _normalize_nist_id(fde[key]["title"])
        if nist_id is None:
            # Preserved verbatim so `apply_crosswalk` can report it rather
            # than the row vanishing silently.
            nist_id = f"?{fde[key]['title'].strip()}"
        mapping.setdefault(citation, [])
        if nist_id not in mapping[citation]:
            mapping[citation].append(nist_id)
    # Sorted so the parse is deterministic regardless of CPRT's row order.
    return {citation: sorted(nist_ids, key=_sort_key) for citation, nist_ids in mapping.items()}


def fetch_cprt_crosswalk(*, version: str = CPRT_FRAMEWORK_VERSION) -> dict:
    """Fetch the raw CPRT element lists for the HIPAA-to-800-53 crosswalk.

    Kept separate from `parse_cprt_crosswalk` — the only network-touching
    function here — so the parser stays pure and testable offline against the
    fixture in tests/fixtures/cprt_hipaa_to_800-53r5.json.
    """
    import requests

    payload = {}
    for element_type in CPRT_ELEMENT_TYPES:
        response = requests.get(
            CPRT_ELEMENTS_URL.format(version=version, element_type=element_type), timeout=60
        )
        response.raise_for_status()
        payload[element_type] = response.json()
    return payload


def apply_crosswalk(controls: list[Control], mapping: dict[str, list[str]]) -> CrosswalkReport:
    """Attach `mapping` to `controls` in place as `source_crosswalk["nist"]`.

    Values follow the free-text convention the rest of the pipeline reads
    (see mapping/crosswalk.py): comma-separated SP 800-53 IDs, e.g.
    "IA-2, IA-2(1), IA-8".
    """
    targets: dict[str, Control | object] = {}
    for control in controls:
        targets[control.control_id] = control
        for enhancement in control.enhancements:
            targets[enhancement.enhancement_id] = enhancement

    report = CrosswalkReport()
    resolved: dict[str, set[str]] = {}

    for citation, nist_ids in mapping.items():
        target_id = CITATION_ALIASES.get(citation, citation)
        if target_id not in targets:
            if citation not in report.unmatched_citations:
                report.unmatched_citations.append(citation)
            continue
        for nist_id in nist_ids:
            if nist_id.startswith("?"):
                raw = nist_id[1:]
                if raw not in report.unparsed_nist_ids:
                    report.unparsed_nist_ids.append(raw)
                continue
            resolved.setdefault(target_id, set()).add(nist_id)

    for target_id, nist_ids in resolved.items():
        target = targets[target_id]
        target.source_crosswalk["nist"] = ", ".join(sorted(nist_ids, key=_sort_key))
        if isinstance(target, Control):
            report.mapped_controls += 1
        else:
            report.mapped_enhancements += 1

    report.unmatched_citations.sort()
    report.unparsed_nist_ids.sort()
    report.unmapped_requirements = sorted(set(targets) - set(resolved))
    return report
