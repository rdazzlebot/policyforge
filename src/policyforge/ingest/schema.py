"""Common shape every framework loader normalizes into.

Keeping ingest/*.py loaders separate from this schema is what lets bundled
(public-domain) sources and BYOC (licensed) sources flow through the same
mapping/synthesis/generate pipeline without the pipeline code caring where
a Control came from.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ControlEnhancement:
    enhancement_id: str
    title: str
    baseline: str
    description: str


@dataclass
class Control:
    control_id: str
    title: str
    framework: str          # e.g. "NIST-800-53", "FedRAMP", "ARC-AMPE", "HITRUST-CSF", "GovRAMP"
    framework_version: str  # e.g. "Rev 5", "v11.8"
    family: str | None = None
    family_abbr: str | None = None
    baseline: str | None = None
    control_statement: str = ""
    discussion: str = ""
    enhancements: list[ControlEnhancement] = field(default_factory=list)
    related_controls: list[str] = field(default_factory=list)
    # Raw framework-ID crosswalk as captured at the source (e.g. the HITRUST
    # column in a NIST control note). Kept separate from mapping/crosswalk.py's
    # curated crosswalk so provenance is always traceable back to the loader
    # that produced it.
    source_crosswalk: dict[str, str] = field(default_factory=dict)
    source_path: str | None = None
