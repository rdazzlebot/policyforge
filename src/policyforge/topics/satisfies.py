"""What a published document can be shown against: the assessor's direction.

`addresses` answers "who answers for AC-2". `coverage` answers it in
aggregate. Neither answers the question an assessor actually opens with —
*this document, what does it satisfy?* — and answering it by hand means
reading every citation in the text and following each one through the
crosswalk.

**The evidence is the citations in the document, not the topic's anchors.**
A topic anchor is an intention: somebody wrote down that this team owns
AC-2. A citation in published text is the thing an assessor can be shown. So
a requirement reaches this report only when a document cites it, or cites a
control the crosswalk maps it to, and a requirement the topic anchors while
its documents never mention it is reported apart, under its own heading. That
gap is the most useful line here: it is the difference between what a
programme claims and what it has written down.

**Every mapping says where it came from.** A pair from the catalog's own
published crosswalk, a pair the organization reviewed and accepted, and a
pair sitting in an overlay that nobody has looked at yet are three different
strengths of evidence, and an assessor is entitled to tell them apart. The
unreviewed ones are listed and marked rather than hidden: a report that
quietly dropped them would look better than the evidence behind it, which is
the failure this project exists to avoid. Where a reviewed pair records a
relationship of `superset` or `intersects` — the control covers part of the
requirement — it is reported as *in part*, never as satisfied.

Deterministic: no model call and no network, like `coverage` and
`addresses`. Requirement identifiers are printed; requirement text and
titles are not, which is the same line the other analyses hold and keeps a
licensed catalog's prose out of a report that gets pasted around.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from policyforge.mapping.crosswalk import normalize_framework

_HEADING_RE = re.compile(r"^#{1,6}\s+(?P<title>.+?)\s*$")
#: `AC-2(3)` -> `AC-2`. The same shape `coverage._parent_of` matches.
_ENHANCEMENT_RE = re.compile(r"^([A-Za-z]{2}-\d+)\(\d+\)$")


def _parent_of(requirement_id: str) -> str | None:
    match = _ENHANCEMENT_RE.match(requirement_id)
    return match.group(1) if match else None


PUBLISHED = "published crosswalk"
REVIEWED = "overlay, reviewed"
UNREVIEWED = "overlay, NOT REVIEWED"

#: Relationships under which the control covers only part of the requirement.
#: The same reading `coverage` uses.
PARTIAL = frozenset({"superset", "intersects"})


@dataclass
class Citation:
    """One requirement named in a document, and where."""

    framework: str
    requirement_id: str
    #: What the tag said after the id, if anything — a baseline ("Moderate,
    #: High"), HIPAA's "Addressable", ARC-AMPE's "AE Mandatory". Kept as
    #: written: it is the framework's own word for how the requirement
    #: applies, and paraphrasing it would be inventing a vocabulary.
    qualifier: str = ""
    sections: list[str] = field(default_factory=list)

    @property
    def key(self) -> tuple[str, str]:
        return (self.framework, self.requirement_id)


@dataclass
class Reached:
    """A requirement reached from a cited control through the crosswalk."""

    framework: str
    requirement_id: str
    via: str
    provenance: str = PUBLISHED
    relationship: str = "unspecified"
    reviewed_by: str = ""
    flags: list[str] = field(default_factory=list)
    sections: list[str] = field(default_factory=list)

    @property
    def in_part(self) -> bool:
        return self.relationship in PARTIAL

    @property
    def reviewed(self) -> bool:
        return self.provenance == REVIEWED


@dataclass
class DocumentEvidence:
    path: str
    title: str
    tier: str = ""
    topic: str = ""
    cited: list[Citation] = field(default_factory=list)
    reached: list[Reached] = field(default_factory=list)
    #: Anchors of the document's topic that no document of that topic cites.
    anchored_not_cited: list[str] = field(default_factory=list)
    #: Cited identifiers that match no requirement in any loaded catalog.
    unknown: list[str] = field(default_factory=list)

    @property
    def unreviewed(self) -> list[Reached]:
        return [r for r in self.reached if r.provenance == UNREVIEWED]


def split_citation(part: str, frameworks: list[str], ids=None) -> tuple[str, str, str]:
    """One citation's (framework, requirement id, qualifier).

    None of the three can be found by counting words, in either direction.
    Framework names carry spaces — the generator writes `NIST 800-53 IR-1`
    and `HIPAA Security Rule 164.308(a)(6)(i)`, not `NIST IR-1` — so taking
    the first word as the framework leaves `800-53 IR-1` as the identifier.
    Requirement ids carry spaces too: HITRUST builds them as `01.a Level
    1`, so taking the last word fails from the other end. And a tag may end
    in a qualifier, which the synthesis prompt asks for ("Include the
    baseline in the tag when the source control specifies one, e.g.
    `[GovRAMP IA-5 Moderate]`") and whose vocabulary is per-framework and
    open-ended: `IR-4(1) Moderate, High`, `164.310(a)(2)(i) Addressable`,
    `CP-2 AE Mandatory`.

    So neither end is guessed. The framework is split on the names the
    loaded catalogs declare, longest first and only at a word boundary;
    then the identifier is the *longest run of words that the catalog
    actually has an id for*, and whatever follows is the qualifier. Asking
    the catalog means there is no vocabulary to keep up to date, and
    HITRUST's `01.a Level 1` resolves whole because the catalog says that
    is one id.

    A citation whose id resolves to nothing is returned entire, with no
    qualifier split off, so it is reported as written rather than as a
    truncation this function invented.
    """
    lowered = part.casefold()
    for name in frameworks:
        if lowered.startswith(name.casefold()) and part[len(name) : len(name) + 1].isspace():
            framework, rest = name, part[len(name) :].strip()
            break
    else:
        framework, _, rest = part.partition(" ")
        rest = rest.strip()

    words = rest.split()
    known = (ids or {}).get(normalize_framework(framework), ())
    for count in range(len(words), 0, -1):
        candidate = " ".join(words[:count])
        if candidate in known:
            return framework, candidate, " ".join(words[count:])
    return framework, rest, ""


def parse_citations(body: str, frameworks=(), ids=None) -> list[tuple[str, str, str, str]]:
    """(framework, requirement id, qualifier, section) for each citation in `body`.

    A tag is `[NIST 800-53 AC-2 | HIPAA Security Rule 164.308(a)(3)(i)]` —
    one or more citations separated by `|`. The pattern matching the tag
    itself is the one `edit/apply.py` defines and `content/check.py`
    already borrows: this report has to agree with the checker about what a
    citation *is*, and two regexes would eventually disagree.

    The section is the nearest heading above the citation, so a reader can
    be pointed at the paragraph rather than the file.
    """
    from policyforge.edit.apply import _SOURCE_TAG_RE

    known = sorted({str(f) for f in frameworks}, key=len, reverse=True)
    found: list[tuple[str, str, str, str]] = []
    section = ""
    for line in body.splitlines():
        heading = _HEADING_RE.match(line.strip())
        if heading:
            section = heading.group("title")
            continue
        for tag in _SOURCE_TAG_RE.findall(line):
            for part in tag.strip("[]").split("|"):
                framework, requirement_id, qualifier = split_citation(part.strip(), known, ids)
                if framework and requirement_id:
                    found.append((framework, requirement_id, qualifier, section))
    return found


def _catalog_index(controls) -> dict[str, set[str]]:
    """{normalized framework: every requirement id it holds}."""
    index: dict[str, set[str]] = {}
    for control in controls:
        ids = index.setdefault(normalize_framework(control.framework), set())
        ids.add(control.control_id)
        ids.update(e.enhancement_id for e in control.enhancements)
        ids.update(r.requirement_id for r in control.requirements)
    return index


def document_evidence(
    document,
    *,
    controls,
    crosswalk: dict[str, dict[str, list[str]]],
    provenance: dict[tuple[str, str, str], object] | None = None,
) -> DocumentEvidence:
    """What one document can be shown against.

    `anchored_not_cited` is left empty here and filled by `build_report`,
    which can see the topic's other documents; see its docstring for why
    that question cannot be answered one file at a time.

    `provenance` maps (framework, requirement id, anchor id) to the overlay
    row that accepted the pair, from `crosswalk.overlay.accepted_rows`. A
    pair with no entry came from the catalog's published crosswalk.

    `controls` must be the catalogs as `load_catalogs` returns them, with
    overlays already applied, since the crosswalk is read from them.
    """
    index = _catalog_index(controls)
    evidence = DocumentEvidence(
        path=getattr(document, "relative_path", str(getattr(document, "path", ""))),
        title=document.title,
        tier=getattr(document, "tier", ""),
        topic=getattr(document, "topic", ""),
    )

    cited: dict[tuple[str, str], Citation] = {}
    names = {c.framework for c in controls}
    for framework, requirement_id, qualifier, section in parse_citations(
        document.body, names, index
    ):
        key = (normalize_framework(framework), requirement_id)
        # Checked against the framework the citation names, not against every
        # id in every catalog: `[HIPAA AC-2]` names a real NIST control under
        # the wrong framework, and an assessor following it finds nothing.
        if requirement_id not in index.get(key[0], ()):
            label = f"{framework} {requirement_id}"
            if label not in evidence.unknown:
                evidence.unknown.append(label)
            continue
        citation = cited.setdefault(key, Citation(key[0], requirement_id, qualifier))
        if section and section not in citation.sections:
            citation.sections.append(section)
    evidence.cited = sorted(cited.values(), key=lambda c: (c.framework, c.requirement_id))

    anchor_ids = {c.requirement_id for c in evidence.cited if c.framework == "nist"}
    reached: dict[tuple[str, str], Reached] = {}
    for anchor in sorted(anchor_ids):
        sections = next(
            (c.sections for c in evidence.cited if c.key == ("nist", anchor)),
            [],
        )
        for raw_framework, requirement_ids in sorted(crosswalk.get(anchor, {}).items()):
            framework = normalize_framework(raw_framework)
            for requirement_id in sorted(requirement_ids):
                key = (framework, requirement_id)
                if key in cited or key in reached:
                    continue
                row = (provenance or {}).get((framework, requirement_id, anchor))
                reached[key] = Reached(
                    framework=framework,
                    requirement_id=requirement_id,
                    via=anchor,
                    provenance=_provenance_of(row),
                    relationship=getattr(row, "relationship", "unspecified") or "unspecified",
                    reviewed_by=str((getattr(row, "reviewed_by", {}) or {}).get("who", "")),
                    flags=list(getattr(row, "flags", []) or []),
                    sections=list(sections),
                )
    evidence.reached = sorted(reached.values(), key=lambda r: (r.framework, r.requirement_id))
    return evidence


def build_report(
    documents,
    *,
    controls,
    crosswalk: dict[str, dict[str, list[str]]],
    provenance: dict[tuple[str, str, str], object] | None = None,
    topics=(),
) -> list[DocumentEvidence]:
    """Evidence for each of `documents`, in the order given.

    "Anchored but cited nowhere" is settled across a topic's documents
    together rather than per file. A topic's Policy, Standard and Procedure
    share its anchors between them — the Procedure is usually where a
    control is actually cited — so asking the question of one document at a
    time would report the Policy as missing anchors its own Procedure
    cites, which is noise, and noise in the one section an assessor should
    read first.

    Only documents present in `documents` count as citing. Narrowing to one
    topic therefore still gives that topic a true answer, while `--document`
    on a single file reports against that file alone, which is what naming
    one file asks for.
    """
    from policyforge.zardoz.corpus import slugify

    # Keyed by slug, not by name, and the document is matched on its
    # frontmatter topic *or* its filename: `generate` names the file for the
    # topic's slug but writes no `topic:` — that arrives at publish — so a
    # name-only match would report nothing for a tree that was just
    # generated. See the same fallback in the `satisfies` command.
    anchors_of = {slugify(t.name): list(t.nist_controls) for t in topics}
    evidences = []
    keys = []
    for document in documents:
        evidence = document_evidence(
            document, controls=controls, crosswalk=crosswalk, provenance=provenance
        )
        slug = slugify(evidence.topic)
        if slug not in anchors_of:
            slug = slugify(getattr(document, "slug", "") or "")
        evidences.append(evidence)
        keys.append(slug)

    cited_by_topic: dict[str, set[str]] = {}
    for evidence, slug in zip(evidences, keys, strict=True):
        reached = cited_by_topic.setdefault(slug, set())
        for citation in evidence.cited:
            if citation.framework != "nist":
                continue
            reached.add(citation.requirement_id)
            # Citing AC-2(3) is mentioning AC-2: the enhancement is part of
            # the control it enhances. `coverage` reads the relation the
            # other way round (anchoring AC-2 claims AC-2(3)) and `drift`
            # the same way this does, so a topic that cites IR-3(1) and
            # IR-3(3) is not reported as never mentioning IR-3.
            parent = _parent_of(citation.requirement_id)
            if parent:
                reached.add(parent)
    for evidence, slug in zip(evidences, keys, strict=True):
        if slug in anchors_of:
            evidence.anchored_not_cited = sorted(
                set(anchors_of[slug]) - cited_by_topic.get(slug, set())
            )
    return evidences


def _provenance_of(row) -> str:
    """How strong the evidence for one accepted pair is.

    Three cases, and the middle one is why this is not just a truth test on
    `reviewed_by`: `seed_overlay` writes the catalog's published pairs in as
    accepted with `sources: [published]` and no reviewer, because nobody
    reviewed them — they came with the catalog. Those are published-crosswalk
    evidence, exactly as they were before the overlay existed, and calling
    them unreviewed would flag every row of a freshly seeded file.

    What is left is a pair accepted in the file with no reviewer and no
    publisher behind it: a model proposal somebody marked accepted by hand
    rather than through `crosswalk review`. That is the one an assessor
    needs pointed out.
    """
    if row is None:
        return PUBLISHED
    if getattr(row, "reviewed_by", None):
        return REVIEWED
    if "published" in (getattr(row, "sources", None) or []):
        return PUBLISHED
    return UNREVIEWED


def as_records(evidences: list[DocumentEvidence]) -> list[dict]:
    """The JSON form. A contract once anything scripts it, so field names stay."""
    return [
        {
            "document": e.path,
            "title": e.title,
            "tier": e.tier,
            "topic": e.topic,
            "cited": [
                {
                    "framework": c.framework,
                    "requirement_id": c.requirement_id,
                    "qualifier": c.qualifier,
                    "sections": c.sections,
                    "route": "cited",
                }
                for c in e.cited
            ],
            "reached": [
                {
                    "framework": r.framework,
                    "requirement_id": r.requirement_id,
                    "route": "crosswalked",
                    "via": r.via,
                    "provenance": r.provenance,
                    "relationship": r.relationship,
                    "in_part": r.in_part,
                    "reviewed_by": r.reviewed_by,
                    "flags": r.flags,
                    "sections": r.sections,
                }
                for r in e.reached
            ],
            "anchored_not_cited": e.anchored_not_cited,
            "unknown_citations": e.unknown,
        }
        for e in evidences
    ]


def _by_framework(items) -> dict[str, list]:
    grouped: dict[str, list] = {}
    for item in items:
        grouped.setdefault(item.framework, []).append(item)
    return grouped


def format_report(evidences: list[DocumentEvidence]) -> str:
    lines: list[str] = []
    for evidence in evidences:
        lines.append(f"{evidence.path} — {evidence.title}")
        lines.append("=" * 60)
        if evidence.topic:
            lines.append(f"  topic: {evidence.topic}")
        if not evidence.cited:
            lines.append("  Cites no framework requirement. Nothing here is traceable.")
        for framework, citations in sorted(_by_framework(evidence.cited).items()):
            lines.append("")
            lines.append(f"Cited directly — {framework.upper()} ({len(citations)})")
            lines.append("-" * 60)
            for citation in citations:
                where = ", ".join(citation.sections) or "no section heading"
                shown = citation.requirement_id
                if citation.qualifier:
                    shown += f" ({citation.qualifier})"
                lines.append(f"  {shown:<28} {where}")
        for framework, reached in sorted(_by_framework(evidence.reached).items()):
            lines.append("")
            lines.append(f"Reached through the crosswalk — {framework.upper()} ({len(reached)})")
            lines.append("-" * 60)
            for item in reached:
                extent = "in part" if item.in_part else "satisfied"
                note = item.provenance
                if item.reviewed_by:
                    note += f" by {item.reviewed_by}"
                if item.relationship != "unspecified":
                    note += f", {item.relationship}"
                if item.flags:
                    note += f", {', '.join(item.flags)}"
                lines.append(f"  {item.requirement_id:<24} {extent:<10} via {item.via}  [{note}]")
        unreviewed = [r for r in evidence.reached if r.provenance == UNREVIEWED]
        if unreviewed:
            lines.append("")
            lines.append(
                f"  {len(unreviewed)} mapping(s) above rest on an overlay entry NOBODY HAS "
                "REVIEWED. They are shown because hiding them would make this report look "
                "stronger than the evidence. Review them with `policyforge crosswalk review` "
                "before handing this to an assessor."
            )
        if evidence.anchored_not_cited:
            lines.append("")
            lines.append(
                f"Anchored by the topic, cited nowhere ({len(evidence.anchored_not_cited)})"
            )
            lines.append("-" * 60)
            lines.append(
                "  The registry says this topic answers for these; its documents never "
                "mention them. This is the gap between what is claimed and what is written."
            )
            for index in range(0, len(evidence.anchored_not_cited), 8):
                lines.append("  " + ", ".join(evidence.anchored_not_cited[index : index + 8]))
        if evidence.unknown:
            lines.append("")
            lines.append(f"Cited but unknown to every loaded catalog ({len(evidence.unknown)})")
            lines.append("-" * 60)
            lines.append(
                "  Either mistyped, or from a framework nobody loaded. An assessor "
                "following one of these finds nothing."
            )
            lines.append("  " + ", ".join(evidence.unknown))
        lines.append("")
    return "\n".join(lines)
