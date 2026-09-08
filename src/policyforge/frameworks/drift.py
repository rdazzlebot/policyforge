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
import re
import subprocess  # nosec B404
from dataclasses import dataclass, field
from pathlib import Path

ADDED = "added"
REMOVED = "removed"
CHANGED = "changed"

#: Fields whose change alters what the organization must *do*. Everything
#: else is editorial: worth recording, not worth re-opening a document over.
SUBSTANTIVE_FIELDS = ("control_statement", "baseline", "enhancements", "parameters")

#: Inline source tags in a generated document — `[NIST AC-2 | HIPAA 164.x]`.
#: How a document says which control it answers for, and therefore how this
#: works out which documents a control change reaches.
_SOURCE_TAG_RE = re.compile(r"\[(?:NIST|HIPAA|FedRAMP|HITRUST|GovRAMP|ARC-AMPE)\s[^\]]*\]")
_CONTROL_ID_RE = re.compile(r"\b([A-Z]{2}-\d+(?:\(\d+\))?)")


def _normalize(text: str) -> str:
    """Collapse whitespace so a reflow does not read as a rewrite."""
    return " ".join((text or "").split())


def _base_control(control_id: str) -> str:
    return control_id.split("(")[0].strip().upper()


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

    return changes


def documents_citing(controls: set[str], root: Path) -> dict[str, list[str]]:
    """Control id -> the documents whose source tags cite it.

    Walks the content tree rather than the corpus, because the question is
    which *files you maintain* need re-reading, and those are the ones under
    review in a pull request.
    """
    from policyforge.content.tree import load_content_tree

    hits: dict[str, list[str]] = {}
    if not root.exists():
        return hits

    documents, _ = load_content_tree(root)
    for document in documents:
        cited: set[str] = set()
        for tag in _SOURCE_TAG_RE.findall(document.body):
            cited.update(_CONTROL_ID_RE.findall(tag))
        for control_id in cited:
            # A document citing AC-2 is reached by a change to AC-2(1) too:
            # the enhancement is part of the control it enhances, and a
            # reader who has to re-check one has to re-check the other.
            for changed in controls:
                if changed == control_id or _base_control(changed) == _base_control(control_id):
                    hits.setdefault(changed, []).append(document.relative_path)
    return {key: sorted(set(value)) for key, value in hits.items()}


def assess_impact(changes, *, topics=(), content_root=None, decisions=None) -> dict[str, Impact]:
    """Work out what each changed control reaches."""
    changed_ids = {c.control_id for c in changes}
    impacts = {control_id: Impact(control_id=control_id) for control_id in changed_ids}

    for topic in topics or ():
        anchors = {a.upper() for a in getattr(topic, "nist_controls", [])}
        for control_id in changed_ids:
            # An anchor claims its enhancements, the same rule coverage.py
            # uses, so a change to AC-2(3) reaches the topic anchoring AC-2.
            if control_id.upper() in anchors or _base_control(control_id) in anchors:
                impacts[control_id].topics.append(topic.name)

    if content_root is not None:
        for control_id, paths in documents_citing(changed_ids, Path(content_root)).items():
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
    try:
        result = subprocess.run(  # nosec B603 B607
            ["git", "show", f"{revision}:{Path(path).as_posix()}"],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout if result.returncode == 0 and result.stdout.strip() else None


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


def analyze_drift(
    old_controls, new_controls, *, topics=(), content_root=None, decisions=None
) -> DriftReport:
    changes = diff_catalogs(old_controls, new_controls)
    return DriftReport(
        old_version=(old_controls[0].framework_version if old_controls else ""),
        new_version=(new_controls[0].framework_version if new_controls else ""),
        changes=changes,
        impacts=assess_impact(
            changes, topics=topics, content_root=content_root, decisions=decisions
        ),
    )
