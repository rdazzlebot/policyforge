"""Coverage and ownership analysis over the topic registry.

Answers the two questions that sink a compliance program, both of which are
set arithmetic once topics are declared — no LLM involved:

* **Orphaned** — an in-scope control no topic claims. Nobody is doing it, and
  nobody knows nobody is doing it.
* **Contested** — an in-scope control two or more topics claim. This is the
  worse failure of the two: on paper it looks covered, while each owner
  assumes the other has it. Ambiguous ownership is precisely what the "one
  topic, one team" model exists to prevent, so it should be a report you run
  rather than a discovery you make during an assessment.

**Claim resolution.** Anchoring a control claims that control *and* its
enhancements, so a topic needn't enumerate AC-2(1)..AC-2(13) to own AC-2. A
topic may also anchor an enhancement directly, and a direct claim beats an
inherited one — that's how AC-2(1) can sit with a different team than AC-2
without either becoming contested.

**Other frameworks come along for free.** Topics anchor NIST controls, but
the crosswalk means a claimed NIST control also accounts for the HIPAA (or
FedRAMP, or HITRUST) requirements mapped to it. `framework_coverage`
reports, per framework, which requirements are reachable from some topic and
which aren't — the same orphan question asked from the assessor's side.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from policyforge.ingest.schema import Control
from policyforge.mapping.crosswalk import normalize_framework
from policyforge.topics.registry import Topic

_ENHANCEMENT_RE = re.compile(r"^([A-Za-z]{2}-\d+)\(\d+\)$")


@dataclass
class FrameworkCoverage:
    """How much of one non-NIST framework the topics reach, via the crosswalk."""

    framework: str
    covered: list[str] = field(default_factory=list)
    uncovered: list[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.covered) + len(self.uncovered)


@dataclass
class CoverageReport:
    scope: str
    in_scope: list[str] = field(default_factory=list)
    #: requirement id -> the single topic that owns it
    covered: dict[str, str] = field(default_factory=dict)
    #: in-scope ids no topic claims
    orphaned: list[str] = field(default_factory=list)
    #: requirement id -> the competing topic names
    contested: dict[str, list[str]] = field(default_factory=dict)
    #: topic name -> anchors that match no control in the catalog (typos)
    unknown_anchors: dict[str, list[str]] = field(default_factory=dict)
    #: topic name -> anchors that are real controls but outside the current
    #: scope. Not an error: the PM and PT families sit in no baseline at all,
    #: and a topic legitimately anchors High-only controls while you analyze
    #: Moderate.
    out_of_scope_anchors: dict[str, list[str]] = field(default_factory=dict)
    #: owner -> number of in-scope requirements they answer for
    by_owner: dict[str, int] = field(default_factory=dict)
    #: topic name -> number of in-scope requirements it claims
    by_topic: dict[str, int] = field(default_factory=dict)
    framework_coverage: list[FrameworkCoverage] = field(default_factory=list)

    @property
    def is_clean(self) -> bool:
        """True when every in-scope control has exactly one owner and every
        anchor resolves."""
        return not (self.orphaned or self.contested or self.unknown_anchors)


def _parent_of(requirement_id: str) -> str | None:
    match = _ENHANCEMENT_RE.match(requirement_id)
    return match.group(1) if match else None


def _in_scope_ids(controls: list[Control]) -> list[str]:
    ids: list[str] = []
    for control in controls:
        ids.append(control.control_id)
        ids.extend(e.enhancement_id for e in control.enhancements)
    return ids


def analyze_coverage(
    topics: list[Topic],
    nist_controls: list[Control],
    *,
    catalog: list[Control] | None = None,
    scope: str = "all controls",
    other_controls: list[Control] | None = None,
    crosswalk: dict[str, dict[str, list[str]]] | None = None,
) -> CoverageReport:
    """Compute ownership coverage of `nist_controls` by `topics`.

    `nist_controls` should already be narrowed to whatever scope you care
    about — a baseline, say — since "orphaned" is only meaningful relative to
    a defined scope. Pass the full, unfiltered catalog as `catalog` so an
    anchor that's merely out of scope can be told apart from one that's a
    typo; without it, every anchor outside the scope looks like a bad ID.
    """
    report = CoverageReport(scope=scope)
    report.in_scope = _in_scope_ids(nist_controls)
    in_scope = set(report.in_scope)
    catalog_ids = set(_in_scope_ids(catalog)) if catalog is not None else set(in_scope)

    direct: dict[str, list[str]] = {}
    inherited: dict[str, list[str]] = {}
    children: dict[str, list[str]] = {}
    for requirement_id in report.in_scope:
        parent = _parent_of(requirement_id)
        if parent:
            children.setdefault(parent, []).append(requirement_id)

    for topic in topics:
        for anchor in topic.nist_controls:
            if anchor not in catalog_ids:
                report.unknown_anchors.setdefault(topic.name, []).append(anchor)
                continue
            if anchor not in in_scope:
                report.out_of_scope_anchors.setdefault(topic.name, []).append(anchor)
                continue
            direct.setdefault(anchor, []).append(topic.name)
            # Anchoring a control also claims its enhancements.
            for child in children.get(anchor, []):
                inherited.setdefault(child, []).append(topic.name)

    owner_of = {t.name: t.owner for t in topics}
    for requirement_id in report.in_scope:
        # A direct claim beats an inherited one, so a specifically-anchored
        # enhancement can sit with a different team than its parent without
        # either being reported as contested.
        claimants = direct.get(requirement_id) or inherited.get(requirement_id) or []
        unique = sorted(set(claimants))
        if not unique:
            report.orphaned.append(requirement_id)
        elif len(unique) == 1:
            report.covered[requirement_id] = unique[0]
            report.by_topic[unique[0]] = report.by_topic.get(unique[0], 0) + 1
            owner = owner_of[unique[0]]
            report.by_owner[owner] = report.by_owner.get(owner, 0) + 1
        else:
            report.contested[requirement_id] = unique

    for topic in topics:
        report.by_topic.setdefault(topic.name, 0)
        report.by_owner.setdefault(topic.owner, 0)

    if other_controls and crosswalk:
        report.framework_coverage = _framework_coverage(
            other_controls, crosswalk, owned=set(report.covered) | set(report.contested)
        )

    return report


def _framework_coverage(
    other_controls: list[Control],
    crosswalk: dict[str, dict[str, list[str]]],
    *,
    owned: set[str],
) -> list[FrameworkCoverage]:
    """Which non-NIST requirements are reachable from an owned NIST control."""
    reachable: dict[str, set[str]] = {}
    for nist_id in owned:
        for framework, equivalent_ids in crosswalk.get(nist_id, {}).items():
            reachable.setdefault(framework, set()).update(equivalent_ids)

    by_framework: dict[str, list[str]] = {}
    for control in other_controls:
        framework = normalize_framework(control.framework)
        ids = by_framework.setdefault(framework, [])
        ids.append(control.control_id)
        ids.extend(e.enhancement_id for e in control.enhancements)

    coverage: list[FrameworkCoverage] = []
    for framework, requirement_ids in sorted(by_framework.items()):
        hit = reachable.get(framework, set())
        coverage.append(
            FrameworkCoverage(
                framework=framework,
                covered=sorted(r for r in requirement_ids if r in hit),
                uncovered=sorted(r for r in requirement_ids if r not in hit),
            )
        )
    return coverage


def format_report(report: CoverageReport, *, show_all: bool = False) -> str:
    """Render the report for a terminal."""
    lines: list[str] = []
    total = len(report.in_scope)
    owned = len(report.covered)
    lines.append(f"Coverage — scope: {report.scope}")
    lines.append("=" * 60)
    lines.append(f"  In scope        {total}")
    lines.append(f"  Owned           {owned}" + (f" ({owned / total:.0%})" if total else ""))
    lines.append(f"  Orphaned        {len(report.orphaned)}")
    lines.append(f"  Contested       {len(report.contested)}")

    if report.unknown_anchors:
        lines.append("")
        lines.append("Unknown anchors — these control IDs don't exist in the catalog")
        lines.append("-" * 60)
        for topic, anchors in sorted(report.unknown_anchors.items()):
            lines.append(f"  {topic}: {', '.join(anchors)}")

    if report.out_of_scope_anchors:
        total_out = sum(len(a) for a in report.out_of_scope_anchors.values())
        lines.append("")
        lines.append(
            f"Anchored but out of scope ({total_out}) — real controls this scope doesn't include"
        )
        lines.append("-" * 60)
        for topic, anchors in sorted(report.out_of_scope_anchors.items()):
            shown = anchors if show_all else anchors[:10]
            suffix = "" if len(shown) == len(anchors) else f", +{len(anchors) - len(shown)} more"
            lines.append(f"  {topic}: {', '.join(shown)}{suffix}")

    if report.contested:
        lines.append("")
        lines.append("Contested — more than one topic claims these")
        lines.append("-" * 60)
        for requirement_id, topics in sorted(report.contested.items()):
            lines.append(f"  {requirement_id:<12} {' | '.join(topics)}")

    if report.orphaned:
        lines.append("")
        lines.append("Orphaned — no topic claims these")
        lines.append("-" * 60)
        shown = report.orphaned if show_all else report.orphaned[:40]
        for index in range(0, len(shown), 8):
            lines.append("  " + ", ".join(shown[index : index + 8]))
        if len(shown) < len(report.orphaned):
            lines.append(f"  ... and {len(report.orphaned) - len(shown)} more (--show-all)")

    if report.by_owner:
        lines.append("")
        lines.append("Requirements owned, by team")
        lines.append("-" * 60)
        for owner, count in sorted(report.by_owner.items(), key=lambda kv: (-kv[1], kv[0])):
            lines.append(f"  {count:>4}  {owner}")

    for framework in report.framework_coverage:
        lines.append("")
        lines.append(f"{framework.framework.upper()} reachable via the crosswalk")
        lines.append("-" * 60)
        lines.append(
            f"  {len(framework.covered)} of {framework.total} requirements map to an "
            "owned NIST control"
        )
        if framework.uncovered:
            shown = framework.uncovered if show_all else framework.uncovered[:12]
            lines.append("  Not reached:")
            for index in range(0, len(shown), 4):
                lines.append("    " + ", ".join(shown[index : index + 4]))
            if len(shown) < len(framework.uncovered):
                lines.append(
                    f"    ... and {len(framework.uncovered) - len(shown)} more (--show-all)"
                )

    return "\n".join(lines)
