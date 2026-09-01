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

    return crosswalk
