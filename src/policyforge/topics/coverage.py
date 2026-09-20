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

**Reached is not the same as covered.** Where an organization's crosswalk
overlay records how a pair relates, a requirement reached only through
controls recorded as `superset` (the requirement asks for more than the
control does) or `intersects` is reported apart, as reached in part. It may
be fully met by several such controls together, and it may not; no single
owned control is recorded as covering it, and that is a question for a
person, not a count to fold into "covered". A pair with no recorded
relationship counts as reaching the requirement, which is what every pair
did before relationships were recorded.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from policyforge.ingest.schema import Control
from policyforge.mapping.crosswalk import normalize_framework
from policyforge.topics.registry import Topic

#: How a child identifier names its parent, per catalog grammar.
#:
#: **"Anchoring a control also claims its enhancements" is implemented
#: here, so a grammar this does not know silently claims nothing.** A
#: topic anchoring `Govern 1` used to report seven orphans -- no error, a
#: plausible number, and a topic author would have "fixed" it by anchoring
#: all seven subcategories, arriving at a correct-looking registry built
#: around a defect. The workaround looks like diligence, which is what
#: makes the silence expensive.
#:
#: Add a pattern when a catalog becomes anchorable, not before: a grammar
#: listed here for a framework no topic can anchor is untestable.
_PARENT_RES = (
    # 800-53 / FedRAMP / ARC-AMPE: AC-2(1) -> AC-2
    re.compile(r"^([A-Za-z]{2}-\d+)\(\d+\)$"),
    # NIST AI RMF: Govern 1.1 -> Govern 1
    re.compile(r"^([A-Za-z]+ \d+)\.\d+$"),
)

#: Relationships under which one control covers only part of a requirement.
PARTIAL_RELATIONSHIPS = frozenset({"superset", "intersects"})


@dataclass
class FrameworkCoverage:
    """How much of one non-NIST framework the topics reach, via the crosswalk."""

    framework: str
    covered: list[str] = field(default_factory=list)
    uncovered: list[str] = field(default_factory=list)
    #: Reached only through owned controls recorded as covering part of the
    #: requirement (`superset` or `intersects`).
    partial: list[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.covered) + len(self.partial) + len(self.uncovered)


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


def adopted_frameworks(topics, controls) -> set[str]:
    """Framework keys this registry actually anchors identifiers from.

    **"The catalogs a registry anchors" and "the catalogs a registry
    *could* anchor" read the same and are not.** `anchors_a_topic` answers
    the second -- membership in `TOPIC_ANCHORS` -- and using it as the
    coverage scope was correct only while every bundled catalog was either
    always-anchored (800-53) or never-anchorable (HIPAA, the CFR pair).

    The AI RMF is the first that is **anchorable but optional**, and there
    the two diverge with a bill attached: a customer who does no AI
    upgrades, gains 91 requirements in their denominator, and loses six
    points for work they never took on. Measured, not predicted -- 80
    stripped the AI topics out of the example registry and got 1105 in
    scope, 291 orphaned, against 1014 and 200 before.

    **Our own example registry is what hid it**, because it anchors the AI
    RMF and therefore looks fine.

    Adoption is per *catalog*, not per identifier: anchoring one AI RMF id
    brings all 91 into scope. Anything finer would make coverage
    unfalsifiable, since a registry would only ever be measured against
    what it had already claimed.
    """
    from policyforge.mapping.crosswalk import anchors_a_topic

    anchored = {a for topic in topics for a in topic.nist_controls}
    adopted = set()
    for control in controls:
        if not anchors_a_topic(control.framework):
            continue
        identifiers = {control.control_id} | {e.enhancement_id for e in control.enhancements}
        if identifiers & anchored:
            adopted.add(normalize_framework(control.framework))
    return adopted


def split_by_adoption(topics, controls):
    """`(in scope, bundled but unadopted, reachable via the crosswalk)`.

    The middle one exists so an unadopted catalog is **named rather than
    silently absent** -- 80's condition on the ruling, and the same move
    `_zero_row_reasons` already makes for a zero row. Excluding a catalog
    from the denominator is right; making it invisible is not, or the
    exclusion becomes a place for a framework to hide.
    """
    from policyforge.mapping.crosswalk import anchors_a_topic

    adopted = adopted_frameworks(topics, controls)

    # **Adoption only ever NARROWS.** If a registry adopts nothing, the
    # scope is everything anchorable, not nothing.
    #
    # Found by the suite rather than by thinking: a test registry anchoring
    # `ZZ-9` against a catalog of `AC-2` adopts no catalog, because its one
    # anchor is a typo. Without this line the report became "no topic
    # anchors any catalog on disk" -- which silently converts *you have a
    # typo* into *you have no registry*, and `unknown_anchors` exists
    # precisely to say the first.
    #
    # The empty-registry case lands the same way and should: somebody with
    # no topics yet wants to see everything as orphaned, not 0 of 0.
    #
    # This cannot reintroduce the defect the narrowing exists for, because
    # that case -- a real 800-53 registry meeting a newly bundled AI RMF --
    # adopts 800-53 and is never empty.
    if not adopted:
        adopted = {
            normalize_framework(c.framework) for c in controls if anchors_a_topic(c.framework)
        }

    in_scope, unadopted, reachable = [], [], []
    for control in controls:
        if not anchors_a_topic(control.framework):
            reachable.append(control)
        elif normalize_framework(control.framework) in adopted:
            in_scope.append(control)
        else:
            unadopted.append(control)
    return in_scope, unadopted, reachable


def unadopted_note(unadopted) -> list[str]:
    """Report lines naming catalogs that are bundled, anchorable, and
    anchored by nothing."""
    if not unadopted:
        return []
    by_framework: dict[str, int] = {}
    for control in unadopted:
        count = 1 + len(control.enhancements)
        by_framework[control.framework] = by_framework.get(control.framework, 0) + count
    lines = [
        "",
        "Bundled, anchorable, and not adopted",
        "-" * 60,
        "  These are excluded from the numbers above, because a catalog no",
        "  topic anchors is not a gap in your programme -- it is a framework",
        "  you have not taken on. Anchoring any one of its identifiers brings",
        "  the whole catalog into scope.",
    ]
    for name, count in sorted(by_framework.items()):
        lines.append(f"  {name}: {count} requirements, anchored by no topic")
    return lines


def scope_label(controls, baseline: str | None = None) -> str:
    """What the coverage denominator actually contained, named.

    **A percentage whose denominator can change without the reader being
    told is not a measurement.** When the AI RMF became anchorable the
    programme headline fell 80.3% -> 73.7% with the numerator unchanged
    at 814: ninety-one requirements arrived that a topic *could* own and
    none yet does. That is real information and it is indistinguishable,
    from the number alone, from work having been lost.

    The same arithmetic with the opposite meaning caused a live defect
    once already -- every installed catalog was being counted as
    anchorable, so requirements no topic could ever anchor were orphans
    by construction and installing a catalog lowered the score. That was
    wrong and was fixed. This is right and still needs saying, because a
    reader cannot tell the two apart by looking at the percentage.

    So the scope line names the catalogs, and a changed denominator is
    visible in the report rather than inferred from a number moving.
    """
    names = sorted({c.framework for c in controls})
    listed = ", ".join(names) if names else "no anchorable catalog"
    return f"{baseline} baseline ({listed})" if baseline else f"all controls ({listed})"


def _parent_of(requirement_id: str) -> str | None:
    for pattern in _PARENT_RES:
        match = pattern.match(requirement_id)
        if match:
            return match.group(1)
    return None


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
    relationships: dict[tuple[str, str, str], str] | None = None,
) -> CoverageReport:
    """Compute ownership coverage of `nist_controls` by `topics`.

    `nist_controls` should already be narrowed to whatever scope you care
    about — a baseline, say — since "orphaned" is only meaningful relative to
    a defined scope. Pass the full, unfiltered catalog as `catalog` so an
    anchor that's merely out of scope can be told apart from one that's a
    typo; without it, every anchor outside the scope looks like a bad ID.

    `relationships` maps (framework, requirement id, NIST id) to the
    relationship an organization recorded for that pair — see
    `crosswalk.overlay.accepted_relationships`.
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
            other_controls,
            crosswalk,
            owned=set(report.covered) | set(report.contested),
            relationships=relationships or {},
        )

    return report


def _framework_coverage(
    other_controls: list[Control],
    crosswalk: dict[str, dict[str, list[str]]],
    *,
    owned: set[str],
    relationships: dict[tuple[str, str, str], str],
) -> list[FrameworkCoverage]:
    """Which non-NIST requirements are reachable from an owned NIST control."""
    reachable: dict[str, set[str]] = {}
    in_part: dict[str, set[str]] = {}
    for nist_id in owned:
        for framework, equivalent_ids in crosswalk.get(nist_id, {}).items():
            for requirement_id in equivalent_ids:
                relationship = relationships.get((framework, requirement_id, nist_id))
                if relationship in PARTIAL_RELATIONSHIPS:
                    in_part.setdefault(framework, set()).add(requirement_id)
                else:
                    reachable.setdefault(framework, set()).add(requirement_id)

    by_framework: dict[str, list[str]] = {}
    for control in other_controls:
        framework = normalize_framework(control.framework)
        ids = by_framework.setdefault(framework, [])
        ids.append(control.control_id)
        ids.extend(e.enhancement_id for e in control.enhancements)

    coverage: list[FrameworkCoverage] = []
    for framework, requirement_ids in sorted(by_framework.items()):
        hit = reachable.get(framework, set())
        part = in_part.get(framework, set()) - hit
        coverage.append(
            FrameworkCoverage(
                framework=framework,
                covered=sorted(r for r in requirement_ids if r in hit),
                partial=sorted(r for r in requirement_ids if r in part),
                uncovered=sorted(r for r in requirement_ids if r not in hit and r not in part),
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
        if framework.partial:
            lines.append(
                f"  {len(framework.partial)} more are reached only in part — no owned control "
                "is recorded as covering all of the requirement:"
            )
            shown = framework.partial if show_all else framework.partial[:12]
            for index in range(0, len(shown), 4):
                lines.append("    " + ", ".join(shown[index : index + 4]))
            if len(shown) < len(framework.partial):
                lines.append(f"    ... and {len(framework.partial) - len(shown)} more (--show-all)")
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
