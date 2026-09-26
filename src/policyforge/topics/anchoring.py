"""Which ids a topic may anchor to own a requirement: one rule for every caller (#377).

"Which control does this id belong to" (`AC-2(3)` -> `AC-2`, `Govern 1.1` ->
`Govern 1`) was written separately at least seven times: coverage, bundles,
satisfies, drift, discover, the programme's parameter scope, and drift's
own `_topic_keys`. Each copy was found broken on its own (#312, #318, #335,
#339, #345, #369), and the commonest break was the same one: **a rule that
reads no framework**. `Govern 1.1` is an AI RMF subcategory under the
category `Govern 1`, and it is also the id of the Playbook's suggestions for
that subcategory, which no topic owns. A rule given only the id cannot tell
them apart, so it either misses the Core (discover, #345) or claims the
Playbook (programme, #336).

So the rule takes the framework, and the grammar is chosen by it:

    anchor_keys("AC-2(3)", "NIST 800-53")              {"AC-2(3)", "AC-2"}
    anchor_keys("Govern 1.1", "NIST AI RMF")           {"Govern 1.1", "Govern 1"}
    anchor_keys("Govern 1.1", "NIST AI RMF Playbook")  set()

A topic anchoring the parent owns the child, and a topic anchoring the child
owns it directly; which of the two wins is the caller's question (coverage
and bundles prefer the direct claim).

**Two breadths, named, because they answer different questions** (80's
ruling on #377):

- `anchor_keys` is **topic reach**: which team owns this. Only the catalogs
  a topic may anchor, and only the id and the control it hangs off.
- `family_of` is **document reach**: which documents to re-read when this
  changes. Deliberately broader, because missing a document is the
  dangerous direction: every catalog whose ids nest, and the **whole
  family** within the change's own framework. `AC-2(1)` reaches a document
  citing its sibling `AC-2(3)`; `Govern 1.3` reaches one citing `Govern 1`
  or any `Govern 1.x`; a Playbook action reaches Playbook citations of the
  same subcategory and never the Core's.

Ingest code that builds a catalog's own hierarchy (`ingest/ai_rmf.py`)
reads the source, not a topic registry or a document, and stays its own.
"""

from __future__ import annotations

import re

from policyforge.mapping.crosswalk import TOPIC_ANCHORS, normalize_framework

#: How a child id names its parent, per catalog a topic may anchor. Keyed by
#: normalized framework, and **held equal to `TOPIC_ANCHORS`** by
#: `tests/test_anchoring.py`.
#:
#: **A grammar this does not know silently claims nothing** (moved here from
#: `coverage.py`, where it was learned). A topic anchoring `Govern 1` used to
#: report seven orphans: no error, a plausible number, and a topic author
#: would have "fixed" it by anchoring all seven subcategories, arriving at a
#: correct-looking registry built around a defect. The workaround looks like
#: diligence, which is what makes the silence expensive. Hence the test that
#: a catalog made anchorable cannot be missing from this table.
_PARENT_RES: dict[str, re.Pattern[str]] = {
    # AC-2(1) -> AC-2
    "nist-800-53": re.compile(r"^([A-Za-z]{2}-\d+)\(\d+\)$"),
    # Govern 1.1 -> Govern 1
    "nist-ai-rmf": re.compile(r"^([A-Za-z]+ \d+)\.\d+$"),
}


def parent_of(requirement_id: str, framework: str) -> str | None:
    """The control `requirement_id` hangs off in `framework`, or None.

    None for a top-level control, and for any framework a topic cannot
    anchor: the Playbook's `Govern 1.1` has no parent a topic could own.
    """
    rule = _PARENT_RES.get(normalize_framework(framework))
    match = rule.match(requirement_id) if rule else None
    return match.group(1) if match else None


def anchor_keys(requirement_id: str, framework: str) -> frozenset[str]:
    """The ids a topic may anchor to own `requirement_id` from `framework`.

    The id itself and its parent, for a catalog topics anchor; nothing for
    any other catalog, whose requirements a topic reaches only through the
    crosswalk to 800-53 (`ANCHOR_DECISIONS`). Ids are returned as written;
    a caller comparing case-insensitively upper-cases both sides.
    """
    if normalize_framework(framework) not in TOPIC_ANCHORS:
        return frozenset()
    parent = parent_of(requirement_id, framework)
    return frozenset({requirement_id, parent} if parent else {requirement_id})


#: The family grammar for document reach: every catalog whose ids nest, each
#: by its own shape. 800-53's is shared by the catalogs that write 800-53 ids
#: (FedRAMP, ARC-AMPE). The Playbook nests its actions under the subcategory
#: they serve, and stops there: its family is never the Core's category.
_FAMILY_RES: dict[str, re.Pattern[str]] = {
    **_PARENT_RES,
    "fedramp": _PARENT_RES["nist-800-53"],
    "arc-ampe": _PARENT_RES["nist-800-53"],
    # Govern 1.1 Action 3 -> Govern 1.1
    "nist-ai-rmf-playbook": re.compile(r"^([A-Za-z]+ \d+\.\d+) Action \d+$"),
}


def family_of(requirement_id: str, framework: str) -> str:
    """The family `requirement_id` belongs to in `framework`, for document
    reach: the control it hangs off, or itself. Two ids in one framework with
    the same family are re-read together."""
    rule = _FAMILY_RES.get(normalize_framework(framework))
    match = rule.match(requirement_id) if rule else None
    return match.group(1) if match else requirement_id
