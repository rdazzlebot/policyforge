"""What a framework update actually changed, and what it costs you.

A catalog bumps version and the honest question is not "what is different"
— a diff answers that and is unreadable — but **"what do I have to go and
look at?"**. Rev 5.1.1 to 5.2.0 touches a few dozen controls out of a
thousand. Somewhere behind those sits a handful of your topics, a smaller
handful of your published documents, and possibly a parameter you decided on
the strength of wording that has since moved. Everything else is unaffected
and should stay unread.

Without that scoping the two available responses are both wrong. Re-generate
the whole document set, and you throw away every hand edit and every review
that ever happened to it. Change nothing, and the documents quietly stop
matching the catalog they cite. What makes the difference is a blast radius
you can trust, which is why this walks all the way through to *documents*
rather than stopping at control identifiers.

The workflow it is built for is the repo-backed one. `etl-oscal` overwrites
the catalog in place; git still holds the version you had. So the default
comparison is the working copy against the committed one, and "slurp up the
update" is two commands with a report in between:

    policyforge etl-oscal
    policyforge drift --controls data/frameworks/nist-800-53-r5/controls.json

**Not every change is worth reading.** A reworded discussion paragraph is
not a new obligation, so changes are separated by what they touch: the
control statement is the requirement and warrants review, while discussion,
title and related-control edits are noted and kept out of the way. Treating
them alike is how a drift report becomes something people skim past.
"""

from __future__ import annotations

import difflib
import json
import subprocess  # nosec B404
from dataclasses import dataclass, field
from pathlib import Path

ADDED = "added"
REMOVED = "removed"
CHANGED = "changed"

#: Fields whose change alters what the organization must *do*. Everything
#: else is editorial: worth recording, not worth re-opening a document over.
#: `description` is an enhancement's requirement text (#369).
SUBSTANTIVE_FIELDS = ("control_statement", "description", "baseline", "enhancements", "parameters")


def _normalize(text: str) -> str:
    """Collapse whitespace so a reflow does not read as a rewrite."""
    return " ".join((text or "").split())


@dataclass
class ControlChange:
    """One control that arrived, left, or is not what it was."""

    control_id: str
    kind: str
    title: str = ""
    #: Which fields differ. Named rather than summarised so a reader can
    #: decide whether this one matters to them.
    fields: list[str] = field(default_factory=list)
    #: A few lines of the statement diff, for changes to the requirement.
    detail: str = ""

    @property
    def substantive(self) -> bool:
        """Whether this changes what the organization has to do."""
        if self.kind in (ADDED, REMOVED):
            return True
        return any(f in SUBSTANTIVE_FIELDS for f in self.fields)


@dataclass
class Impact:
    """What a changed control reaches."""

    control_id: str
    topics: list[str] = field(default_factory=list)
    documents: list[str] = field(default_factory=list)
    parameters: list[str] = field(default_factory=list)

    @property
    def reaches_anything(self) -> bool:
        return bool(self.topics or self.documents or self.parameters)


def _statement_diff(old: str, new: str, *, context: int = 1) -> str:
    """The changed lines of a statement, not the whole thing."""
    diff = difflib.unified_diff(
        (old or "").splitlines(),
        (new or "").splitlines(),
        lineterm="",
        n=context,
    )
    body = [line for line in diff if line[:1] in "+-" and not line.startswith(("+++", "---"))]
    shown = body[:6]
    if len(body) > 6:
        shown.append(f"    ... {len(body) - 6} more changed line(s)")
    return "\n".join(f"    {line}" for line in shown)


def _enhancement_ids(control) -> set[str]:
    return {e.enhancement_id for e in getattr(control, "enhancements", [])}


def _parameters_of(control) -> set[str]:
    from policyforge.parameters.ledger import extract_parameters

    return {p.key for p in extract_parameters([control])}


def diff_catalogs(old_controls, new_controls) -> list[ControlChange]:
    """Compare two loads of the same framework."""
    old_by_id = {c.control_id: c for c in old_controls}
    new_by_id = {c.control_id: c for c in new_controls}
    changes: list[ControlChange] = []

    for control_id in sorted(set(new_by_id) - set(old_by_id)):
        control = new_by_id[control_id]
        changes.append(ControlChange(control_id=control_id, kind=ADDED, title=control.title))

    for control_id in sorted(set(old_by_id) - set(new_by_id)):
        control = old_by_id[control_id]
        changes.append(ControlChange(control_id=control_id, kind=REMOVED, title=control.title))

    for control_id in sorted(set(old_by_id) & set(new_by_id)):
        old, new = old_by_id[control_id], new_by_id[control_id]
        fields: list[str] = []
        detail = ""

        if _normalize(old.control_statement) != _normalize(new.control_statement):
            fields.append("control_statement")
            detail = _statement_diff(old.control_statement, new.control_statement)
        if (old.baseline or "") != (new.baseline or ""):
            fields.append("baseline")
            detail = detail or f"    baseline: {old.baseline or 'none'} -> {new.baseline or 'none'}"
        if _enhancement_ids(old) != _enhancement_ids(new):
            fields.append("enhancements")
        if _parameters_of(old) != _parameters_of(new):
            fields.append("parameters")
        if _normalize(old.discussion) != _normalize(new.discussion):
            fields.append("discussion")
        if (old.title or "") != (new.title or ""):
            fields.append("title")
        if sorted(old.related_controls) != sorted(new.related_controls):
            fields.append("related_controls")

        if fields:
            changes.append(
                ControlChange(
                    control_id=control_id,
                    kind=CHANGED,
                    title=new.title,
                    fields=fields,
                    detail=detail,
                )
            )
        changes.extend(_enhancement_changes(old, new))

    return changes


def _enhancement_changes(old, new) -> list[ControlChange]:
    """Each enhancement of a control present in both loads that arrived, left,
    or is not what it was, under the ENHANCEMENT's own id (#369).

    **Compared this used to be by id alone**, so a reworded enhancement was
    never reported: measured on the shipped catalogs, 0 changes for 1,573
    enhancements across 8 catalogs, including every 800-53 enhancement, AI
    RMF subcategory and HIPAA implementation specification. The id a user
    cites, and the id impact has to reach (#339), is the enhancement's; the
    parent keeps `fields=["enhancements"]` for an add or remove, as a pointer
    (80's ruling on #369).

    **Fields compared** (named so a later narrowing is visible): the
    `description` (the requirement's text) and `title`, whitespace-normalised
    as `control_statement` is; the `baseline` (HIPAA's Required/Addressable);
    and the parameter ids. Not compared: `additional_requirements` and
    `source_crosswalk`, as at the control level.
    """
    old_by_id = {e.enhancement_id: e for e in getattr(old, "enhancements", [])}
    new_by_id = {e.enhancement_id: e for e in getattr(new, "enhancements", [])}
    found: list[ControlChange] = []
    for eid in sorted(set(new_by_id) - set(old_by_id)):
        found.append(ControlChange(control_id=eid, kind=ADDED, title=new_by_id[eid].title))
    for eid in sorted(set(old_by_id) - set(new_by_id)):
        found.append(ControlChange(control_id=eid, kind=REMOVED, title=old_by_id[eid].title))
    for eid in sorted(set(old_by_id) & set(new_by_id)):
        a, b = old_by_id[eid], new_by_id[eid]
        fields: list[str] = []
        detail = ""
        if _normalize(a.description) != _normalize(b.description):
            fields.append("description")
            detail = _statement_diff(a.description, b.description)
        if (a.baseline or "") != (b.baseline or ""):
            fields.append("baseline")
            detail = detail or f"    baseline: {a.baseline or 'none'} -> {b.baseline or 'none'}"
        if set(a.parameter_values or {}) != set(b.parameter_values or {}):
            fields.append("parameters")
        if _normalize(a.title) != _normalize(b.title):
            fields.append("title")
        if fields:
            found.append(
                ControlChange(
                    control_id=eid, kind=CHANGED, title=b.title, fields=fields, detail=detail
                )
            )
    return found


def documents_citing(
    controls: set[str], root: Path, *, framework: str = "", catalog_ids=(), crosswalk=None
) -> dict[str, list[str]]:
    """Control id -> the documents whose source tags cite its family.

    Walks the content tree rather than the corpus, because the question is
    which *files you maintain* need re-reading, and those are the ones under
    review in a pull request.

    **Document reach, the broader of the two breadths** (`topics.anchoring`,
    80's ruling on #377): a change reaches every document citing the same
    family **in the change's own framework**. A document citing AC-2(3) is
    reached by a change to AC-2(1), because a reader re-checking one part
    of AC-2 has to re-check the control; `Govern 1.3` reaches `Govern 1`
    and every `Govern 1.x`; a Playbook action reaches Playbook citations of
    its subcategory and never the Core's. Missing a document is the
    dangerous direction, so this reaches wider than topic ownership does.

    **Each citation is read with its tag's framework**, resolved against
    the catalog being diffed (`catalog_ids`), so the house shorthand
    `[NIST AC-2]` names it and `[NIST AI RMF Govern 1.3]` does not. This
    matched 800-53-shaped ids in any tag before, so an AI RMF change reached
    no document at all, even one citing it exactly.

    **Across catalogs, through the 800-53 hub** (80's ruling (ii) on #377).
    Every citation stands for 800-53 families: its own if it cites 800-53,
    otherwise those the loaded crosswalk maps it to in full. A change
    reaches a document whose citation shares one with it, whichever catalog
    each names: a FedRAMP change reaches `[NIST 800-53 AC-2]` and
    `[ARC AC-2]`, and an 800-53 change reaches both of those and the HIPAA
    and 800-171 citations mapped to its family. This used to hold by id
    shape between FedRAMP, ARC-AMPE and 800-53 only; through the crosswalk
    it holds for every catalog that carries one, and for none that does not.
    `crosswalk` is `build_crosswalk` over the catalogs actually loaded.
    """
    from policyforge.content.tree import load_content_tree
    from policyforge.mapping.crosswalk import NIST_ANCHOR, normalize_framework
    from policyforge.topics.anchoring import family_of, hubs, reverse_index
    from policyforge.topics.satisfies import parse_citations, resolve_framework

    hits: dict[str, list[str]] = {}
    key = normalize_framework(framework) if framework else ""
    if not root.exists() or not key:
        return hits
    reverse = reverse_index(crosswalk)
    # The catalogs a citation may name: the diffed one, 800-53 (the hub), and
    # every catalog the loaded crosswalk maps. Nothing else can be reached.
    index: dict[str, set[str]] = {key: set(catalog_ids) | set(controls)}
    index.setdefault(NIST_ANCHOR, set()).update(crosswalk or {})
    for catalog, requirement_id in reverse:
        index.setdefault(catalog, set()).add(requirement_id)

    own: dict[str, set[str]] = {}
    hub: dict[str, set[str]] = {}
    for changed in controls:
        own.setdefault(family_of(changed, framework), set()).add(changed)
        for family in hubs(changed, framework, reverse):
            hub.setdefault(family, set()).add(changed)

    def reached(cited: str, requirement_id: str) -> set[str]:
        found = set(own.get(family_of(requirement_id, cited), ())) if cited == key else set()
        for family in hubs(requirement_id, cited, reverse):
            found |= hub.get(family, set())
        return found

    def catalogs_cited(written: str, requirement_id: str) -> list[str]:
        """The loaded catalogs a citation can mean. An abbreviation naming
        two of them (`NIST` with 800-171 and 800-53 both loaded) resolves
        to neither in `resolve_framework`, which is right for a report and
        wrong here: this decides what to re-read, where missing a document
        is the dangerous direction. So it means each catalog it abbreviates
        through which this change reaches the cited id."""
        cited = resolve_framework(written, index)
        if cited:
            return [cited]
        return [
            catalog
            for catalog, ids in index.items()
            if reached(catalog, requirement_id)
            and resolve_framework(written, {catalog: ids}) == catalog
        ]

    documents, _ = load_content_tree(root)
    for document in documents:
        for written, requirement_id, _, _ in parse_citations(document.body, [framework], index):
            for cited in catalogs_cited(written, requirement_id):
                for changed in reached(cited, requirement_id):
                    hits.setdefault(changed, []).append(document.relative_path)
    return {changed: sorted(set(paths)) for changed, paths in hits.items()}


def assess_impact(
    changes,
    *,
    topics=(),
    content_root=None,
    decisions=None,
    framework: str = "",
    catalog_ids=(),
    crosswalk=None,
) -> dict[str, Impact]:
    """Work out what each changed control reaches.

    `framework` is the catalog the changes are in. Topic reach is the one
    rule, `topics.anchoring.topic_keys` (#377): the change's own catalog's
    parent for one topics anchor, and through `crosswalk` for any other, so
    a Playbook change reaches no topic and an 800-171 change reaches the
    topics owning the 800-53 controls NIST maps it to.
    """
    from policyforge.topics.anchoring import topic_keys

    changed_ids = {c.control_id for c in changes}
    impacts = {control_id: Impact(control_id=control_id) for control_id in changed_ids}

    for topic in topics or ():
        anchors = {a.upper() for a in getattr(topic, "nist_controls", [])}
        for control_id in changed_ids:
            keys = {k.upper() for k in topic_keys(control_id, framework, crosswalk)}
            if keys & anchors:
                impacts[control_id].topics.append(topic.name)

    if content_root is not None:
        reached = documents_citing(
            changed_ids,
            Path(content_root),
            framework=framework,
            catalog_ids=catalog_ids,
            crosswalk=crosswalk,
        )
        for control_id, paths in reached.items():
            impacts[control_id].documents.extend(paths)

    for key in decisions or {}:
        control_id = key.split("/")[0].upper()
        for changed in changed_ids:
            if changed.upper() == control_id:
                impacts[changed].parameters.append(key)

    return impacts


@dataclass
class DriftReport:
    old_version: str = ""
    new_version: str = ""
    changes: list[ControlChange] = field(default_factory=list)
    impacts: dict[str, Impact] = field(default_factory=dict)

    @property
    def substantive(self) -> list[ControlChange]:
        return [c for c in self.changes if c.substantive]

    @property
    def editorial(self) -> list[ControlChange]:
        return [c for c in self.changes if not c.substantive]

    @property
    def affected_topics(self) -> list[str]:
        return sorted({t for c in self.substantive for t in self.impacts[c.control_id].topics})

    @property
    def affected_documents(self) -> list[str]:
        return sorted({d for c in self.substantive for d in self.impacts[c.control_id].documents})

    @property
    def affected_parameters(self) -> list[str]:
        return sorted({p for c in self.substantive for p in self.impacts[c.control_id].parameters})

    @property
    def needs_review(self) -> bool:
        return bool(self.substantive)

    def format_report(self, *, limit: int = 25, detail: bool = False) -> str:
        version = f"{self.old_version or 'previous'} -> {self.new_version or 'current'}"
        if not self.changes:
            return f"No change between {version}. Nothing to review."

        added = [c for c in self.changes if c.kind == ADDED]
        removed = [c for c in self.changes if c.kind == REMOVED]
        changed = [c for c in self.changes if c.kind == CHANGED]
        lines = [
            f"{version}: {len(added)} added, {len(removed)} removed, {len(changed)} changed.",
            f"{len(self.substantive)} change(s) alter what the organization must do; "
            f"{len(self.editorial)} are editorial.",
        ]

        if self.substantive:
            lines += ["", "Worth reading:"]
            for change in self.substantive[:limit]:
                what = ", ".join(change.fields) or change.kind
                impact = self.impacts.get(change.control_id, Impact(change.control_id))
                reach = []
                if impact.topics:
                    reach.append(f"topics: {', '.join(impact.topics)}")
                if impact.documents:
                    reach.append(f"docs: {', '.join(impact.documents)}")
                if impact.parameters:
                    reach.append(f"parameters: {', '.join(impact.parameters)}")
                lines.append(f"  {change.kind.upper():7} {change.control_id}  ({what})")
                if reach:
                    lines.append(f"          {' | '.join(reach)}")
                elif change.kind != REMOVED:
                    lines.append("          reaches nothing you have written yet")
                if detail and change.detail:
                    lines.append(change.detail)
            if len(self.substantive) > limit:
                lines.append(f"  ... and {len(self.substantive) - limit} more")

        if self.editorial:
            lines += [
                "",
                f"Editorial only ({len(self.editorial)}): "
                + ", ".join(c.control_id for c in self.editorial[:limit])
                + (" ..." if len(self.editorial) > limit else ""),
            ]

        lines += ["", "Blast radius:"]
        lines.append(
            f"  {len(self.affected_topics)} topic(s): "
            + (", ".join(self.affected_topics) or "none")
        )
        lines.append(
            f"  {len(self.affected_documents)} document(s): "
            + (", ".join(self.affected_documents) or "none")
        )
        lines.append(
            f"  {len(self.affected_parameters)} recorded parameter decision(s): "
            + (", ".join(self.affected_parameters) or "none")
        )
        if self.affected_documents:
            lines += [
                "",
                "Re-read those documents against the new control text. Regenerating "
                "the whole set would discard every hand edit and every review it has "
                "ever had, which is the more expensive mistake.",
            ]
        return "\n".join(lines)


def read_committed(path: Path, *, revision: str = "HEAD") -> str | None:
    """The committed contents of a tracked file, or None.

    This is what makes "run the ETL, then see what changed" work without
    anybody having to snapshot anything first: the ETL overwrites the
    catalog in place and git is still holding the version you had.
    """
    from policyforge.child_output import strict_text

    argv = ["git", "show", f"{revision}:{Path(path).as_posix()}"]
    try:
        result = subprocess.run(argv, capture_output=True, timeout=60, check=False)  # nosec B603 B607
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    # DATA: parsed as the committed catalog a drift is measured against.
    # Before #287 a committed `café` read back as `cafÃ©`, and a byte cp1252
    # leaves undefined crashed with an AttributeError on None.
    text = strict_text(result.stdout, site="drift (committed catalog)", argv=argv)
    return text if text.strip() else None


def _controls_from_json(text: str):
    from policyforge.ingest.schema import Control, ControlEnhancement

    controls = []
    for item in json.loads(text):
        item = dict(item)
        enhancements = [ControlEnhancement(**e) for e in item.pop("enhancements", [])]
        controls.append(Control(enhancements=enhancements, **item))
    return controls


def load_previous(path: Path, *, revision: str = "HEAD"):
    """The previous version of a catalog, from git."""
    text = read_committed(path, revision=revision)
    return _controls_from_json(text) if text else None


def _catalog_ids(controls) -> set[str]:
    """Every control and enhancement id in a catalog."""
    return {c.control_id for c in controls} | {
        e.enhancement_id for c in controls for e in c.enhancements
    }


def analyze_drift(
    old_controls, new_controls, *, topics=(), content_root=None, decisions=None, crosswalk=None
) -> DriftReport:
    """`crosswalk` is `build_crosswalk` over every catalog loaded (the drift
    command passes the installation's); by default, the diffed catalog's
    own two versions, so a call with nothing else loaded reaches only
    through the mapping that catalog carries."""
    from policyforge.mapping.crosswalk import build_crosswalk

    if crosswalk is None:
        crosswalk = build_crosswalk([*(old_controls or []), *(new_controls or [])])
    changes = diff_catalogs(old_controls, new_controls)
    return DriftReport(
        old_version=(old_controls[0].framework_version if old_controls else ""),
        new_version=(new_controls[0].framework_version if new_controls else ""),
        changes=changes,
        impacts=assess_impact(
            changes,
            topics=topics,
            content_root=content_root,
            decisions=decisions,
            framework=(new_controls or old_controls or [None])[0].framework
            if (new_controls or old_controls)
            else "",
            catalog_ids=_catalog_ids(old_controls or []) | _catalog_ids(new_controls or []),
            crosswalk=crosswalk,
        ),
    )
