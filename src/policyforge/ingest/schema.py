"""Common shape every framework loader normalizes into.

Keeping ingest/*.py loaders separate from this schema is what lets bundled
(public-domain) sources and BYOC (licensed) sources flow through the same
mapping/synthesis/generate pipeline without the pipeline code caring where
a Control came from.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ControlEnhancement:
    enhancement_id: str
    title: str
    baseline: str
    description: str
    # Same role as `Control.source_crosswalk` below, but at the
    # sub-requirement level. Some frameworks publish their crosswalk at both
    # levels — NIST's HIPAA-to-800-53 crosswalk, for instance, maps each
    # Required/Addressable implementation specification to its own set of
    # 800-53 controls, distinct from its parent Standard's — so folding
    # those into the parent would lose real mapping detail.
    source_crosswalk: dict[str, str] = field(default_factory=dict)


@dataclass
class Control:
    control_id: str
    title: str
    framework: str  # e.g. "NIST-800-53", "FedRAMP", "ARC-AMPE", "HITRUST-CSF", "GovRAMP"
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


def load_controls(path: Path) -> list[Control]:
    """Load a controls.json produced by any loader's `dataclasses.asdict`
    dump (see `cli.py`'s `etl-vault` command) back into `Control` objects."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    controls = []
    for item in data:
        enhancements = [ControlEnhancement(**e) for e in item.pop("enhancements", [])]
        controls.append(Control(enhancements=enhancements, **item))
    return controls
