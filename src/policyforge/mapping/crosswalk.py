"""Cross-framework control crosswalk.

Builds a NIST-800-53-anchored table of which controls in other frameworks
correspond to each NIST control, the way the source vault's synthesis docs
do it: `{nist_control_id: {framework: [equivalent_ids]}}`.

Two sources of crosswalk data are folded together:

1. A NIST control's own `source_crosswalk` (populated by
   `ingest/nist_vault_loader.py` from its "Cross-Framework Mappings" table).
2. A non-NIST control's `source_crosswalk`, if it happens to point back at a
   NIST control ID (e.g. a FedRAMP control loaded independently that
   declares its own NIST equivalent).

Both are read at the enhancement level as well as the control level: a
framework may publish its crosswalk against sub-requirements rather than
(or as well as) top-level controls. NIST's own HIPAA-to-800-53 crosswalk
does exactly this, mapping each Required/Addressable implementation
specification separately from its parent Standard, so an enhancement's
mapping is recorded under the enhancement's own ID rather than folded into
its parent's.

Crosswalk cell values are free text (e.g. "AC-2 (same ID)", "AC-2, AC-3"),
so IDs are extracted with a regex rather than assumed to be a single clean
token.
"""

from __future__ import annotations

import re

from policyforge.ingest.schema import Control

_ID_RE = re.compile(r"[A-Za-z]{1,4}-\d+(?:\([A-Za-z0-9]+\))?")


def normalize_framework(name: str) -> str:
    """Normalize a framework name: "NIST 800-53" -> "nist", "FedRAMP" -> "fedramp".

    Public because other pipeline stages (e.g. synthesis/merge.py) need to
    look controls up by the same (framework, control_id) key this module
    uses internally.
    """
    return name.strip().lower().split()[0]


def _is_nist(framework: str) -> bool:
    return normalize_framework(framework) == "nist"


def _extract_ids(raw: str) -> list[str]:
    """Pull control/requirement IDs out of a free-text crosswalk cell,
    e.g. "AC-2 (same ID)" -> ["AC-2"], "AC-2, AC-3" -> ["AC-2", "AC-3"]."""
    return _ID_RE.findall(raw)


def _crosswalk_sources(control: Control) -> list[tuple[str, dict[str, str]]]:
    """Every (requirement_id, source_crosswalk) pair a Control carries — the
    control itself, then each of its enhancements. Enhancements are yielded
    under their own IDs so a sub-requirement's mapping stays attributable to
    that sub-requirement."""
    sources = [(control.control_id, control.source_crosswalk)]
    sources.extend((e.enhancement_id, e.source_crosswalk) for e in control.enhancements)
    return [(id_, cw) for id_, cw in sources if cw]


#: HITRUST names its authoritative sources in full ("NIST SP 800-53 r5",
#: "HIPAA Security Rule"), and `normalize_framework` — which keeps the first
#: word — collapses several of them onto the same key. "NIST" alone spans
#: 800-53, 800-171, 800-137 and the Cybersecurity Framework, whose
#: identifiers look nothing alike: `AC-2`, `3.12.4[g]`, `GV.PO-02`. Folding
#: those together would file CSF outcome ids as 800-53 controls, so the
#: distinguishing substring is matched before the first-word fallback.
#:
#: Ordered longest-intent-first: `800-53` is tested before the bare `nist`.
HITRUST_SOURCE_ALIASES: tuple[tuple[str, str], ...] = (
    ("800-53", "nist"),
    ("800-171", "nist-800-171"),
    ("800-172", "nist-800-172"),
    ("800-137", "nist-800-137"),
    ("cybersecurity framework", "nist-csf"),
    ("arc-ampe", "arc-ampe"),
    ("hipaa security rule", "hipaa"),
    ("hipaa privacy rule", "hipaa-privacy"),
    ("hipaa breach", "hipaa-breach"),
    ("fedramp", "fedramp"),
    ("govramp", "govramp"),
    ("iso/iec 27001", "iso-27001"),
    ("iso/iec 27002", "iso-27002"),
    ("pci dss", "pci-dss"),
)

#: Which HITRUST sources are NIST 800-53 proper, and so may anchor a row of
#: the crosswalk. The crosswalk is 800-53-anchored by construction, and an
#: identifier from any other source is not an anchor no matter how much it
#: looks like one.
NIST_ANCHOR = "nist"


def hitrust_framework(source: str) -> str:
    """Normalize one HITRUST authoritative-source name to a framework key."""
    lowered = source.strip().lower()
    for needle, framework in HITRUST_SOURCE_ALIASES:
        if needle in lowered:
            return framework
    return normalize_framework(source) if source.strip() else ""


def _requirement_sources(control: Control) -> list[tuple[str, dict[str, list[str]]]]:
    """Every (requirement_id, {framework: [ids]}) a Control's levels carry.

    HITRUST publishes its crosswalk per *requirement statement* rather than
    per control, because two levels of the same control reference map to
    different places — Level 1 to a handful of 800-53 controls, Level
    FedRAMP to the FedRAMP baseline. Folding them into the control would
    claim mappings for levels that never had them.
    """
    out = []
    for requirement in control.requirements:
        grouped: dict[str, list[str]] = {}
        for source, identifiers in requirement.mappings.items():
            framework = hitrust_framework(source)
            if not framework:
                continue
            merged = grouped.setdefault(framework, [])
            for identifier in identifiers:
                if identifier not in merged:
                    merged.append(identifier)
        if grouped:
            out.append((requirement.requirement_id, grouped))
    return out


def requirement_crosswalk(controls: list[Control]) -> dict[str, dict[str, list[str]]]:
    """`{requirement_id: {framework: [ids]}}` for every level-scoped mapping.

    Kept separate from `build_crosswalk`'s NIST-anchored table on purpose.
    A full CSF library maps to some eighty-odd authoritative sources, and
    pouring all of them into the 800-53 table would bury the frameworks
    this project actually synthesizes against under sources nobody here has
    a catalog for. This function is where the rest stays reachable.
    """
    return {
        requirement_id: mappings
        for control in controls
        for requirement_id, mappings in _requirement_sources(control)
    }


def build_crosswalk(controls: list[Control]) -> dict[str, dict[str, list[str]]]:
    crosswalk: dict[str, dict[str, list[str]]] = {}

    for control in controls:
        if not _is_nist(control.framework):
            continue
        for nist_id, source_crosswalk in _crosswalk_sources(control):
            entry = crosswalk.setdefault(nist_id, {})
            for framework, raw in source_crosswalk.items():
                for id_ in _extract_ids(raw):
                    ids = entry.setdefault(framework, [])
                    if id_ not in ids:
                        ids.append(id_)

    for control in controls:
        if _is_nist(control.framework):
            continue
        framework = normalize_framework(control.framework)
        for requirement_id, source_crosswalk in _crosswalk_sources(control):
            nist_ids: set[str] = set()
            for key, raw in source_crosswalk.items():
                if _is_nist(key):
                    nist_ids.update(_extract_ids(raw))
            for nist_id in nist_ids:
                ids = crosswalk.setdefault(nist_id, {}).setdefault(framework, [])
                if requirement_id not in ids:
                    ids.append(requirement_id)

    # Level-scoped mappings, which only HITRUST publishes. Anchored on the
    # 800-53 identifiers a requirement names, and recorded under the
    # requirement's own id so a reader can see which *level* of a control
    # reference earned the mapping — "01.a Level 1" and "01.a Level FedRAMP"
    # are different answers to the same question.
    for control in controls:
        if _is_nist(control.framework):
            continue
        framework = normalize_framework(control.framework)
        for requirement_id, mappings in _requirement_sources(control):
            for nist_id in mappings.get(NIST_ANCHOR, []):
                for anchor in _extract_ids(nist_id):
                    ids = crosswalk.setdefault(anchor, {}).setdefault(framework, [])
                    if requirement_id not in ids:
                        ids.append(requirement_id)

    return crosswalk
