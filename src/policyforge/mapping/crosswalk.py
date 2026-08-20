"""Cross-framework control crosswalk.

TODO (next build phase): given a list of Control objects from multiple
frameworks (loaded via ingest/*), build a graph/table of which controls
correspond across frameworks, anchored on NIST 800-53 control IDs the way
the source vault's synthesis docs do it. Consider representing this as
{nist_control_id: {framework: [equivalent_ids]}}.
"""

from __future__ import annotations

from policyforge.ingest.schema import Control


def build_crosswalk(controls: list[Control]) -> dict[str, dict[str, list[str]]]:
    raise NotImplementedError("Next build phase — see module docstring.")
