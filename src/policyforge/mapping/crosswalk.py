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

Crosswalk cell values are free text (e.g. "AC-2 (same ID)", "AC-2, AC-3"),
so IDs are extracted with a regex rather than assumed to be a single clean
token.
"""

from __future__ import annotations

import re

from policyforge.ingest.schema import Control

_ID_RE = re.compile(r"[A-Za-z]{1,4}-\d+(?:\([A-Za-z0-9]+\))?")


def normalize_framework(name: str) -> str:
    """"NIST 800-53" -> "nist", "FedRAMP" -> "fedramp", "ARC-AMPE" -> "arc-ampe".

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


def build_crosswalk(controls: list[Control]) -> dict[str, dict[str, list[str]]]:
    crosswalk: dict[str, dict[str, list[str]]] = {}

    for control in controls:
        if not _is_nist(control.framework):
            continue
        entry = crosswalk.setdefault(control.control_id, {})
        for framework, raw in control.source_crosswalk.items():
            for id_ in _extract_ids(raw):
                ids = entry.setdefault(framework, [])
                if id_ not in ids:
                    ids.append(id_)

    for control in controls:
        if _is_nist(control.framework):
            continue
        framework = normalize_framework(control.framework)
        nist_ids: set[str] = set()
        for key, raw in control.source_crosswalk.items():
            if _is_nist(key):
                nist_ids.update(_extract_ids(raw))
        for nist_id in nist_ids:
            ids = crosswalk.setdefault(nist_id, {}).setdefault(framework, [])
            if control.control_id not in ids:
                ids.append(control.control_id)

    return crosswalk
